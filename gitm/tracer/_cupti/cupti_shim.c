/*
 * cupti_shim — a minimal CUPTI Activity API consumer exposed to Python.
 *
 * Why a C shim instead of ctypes: the CUPTI activity record structs
 * (CUpti_ActivityKernel*, CUpti_ActivityMemcpy*, ...) change layout between
 * CUDA versions. Letting the compiler read the *installed* cupti_activity.h
 * means field offsets are always correct — never hand-mirrored in Python where
 * a wrong pad would silently corrupt every kernel timing. The shim copies only
 * primitives into a normalized C record, then Python (gitm.tracer._cupti_decode)
 * turns those into validated trace events.
 *
 * Threading: CUPTI may invoke the buffer-completed callback on its own internal
 * threads during cuptiActivityFlushAll. We therefore do NO Python work in the
 * callbacks — records are appended to a mutex-guarded C array — and only build
 * Python objects in stop(), on the calling thread, holding the GIL.
 *
 * Build: python -m gitm.tracer._cupti.build  (needs the CUDA toolkit + CUPTI).
 *
 * Struct versions below are pinned to CUDA 12.x (Kernel9 / Memcpy5 / Sync).
 * If the deployed CUPTI is older/newer and a versioned struct name is missing,
 * the compile fails loudly — bump the version in the cast, do not guess offsets.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <cupti.h>
#include <cuda_runtime.h>
#include <pthread.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>

#define BUF_SIZE (8 * 1024 * 1024)   /* 8 MiB activity buffers */
#define BUF_ALIGN 8
#define NAME_MAX_LEN 255

/* Normalized record — only the fields GITM consumes. */
typedef struct {
    int      kind;        /* 0 kernel, 1 memcpy, 2 sync */
    char     name[NAME_MAX_LEN + 1];
    uint64_t start_ns;
    uint64_t end_ns;
    uint32_t device_id;
    uint32_t context_id;
    uint32_t stream_id;
    uint32_t correlation_id;
    int32_t  grid[3];
    int32_t  block[3];
    int32_t  static_shared_mem;
    int32_t  dynamic_shared_mem;
    int32_t  registers_per_thread;
    int      copy_kind;
    uint64_t bytes;
    int      sync_type;
} gitm_record;

#define REC_KERNEL 0
#define REC_MEMCPY 1
#define REC_SYNC   2

/* Growable, mutex-guarded record store filled during CUPTI callbacks. */
static gitm_record *g_records = NULL;
static size_t g_count = 0;
static size_t g_cap = 0;
static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
static int g_enabled = 0;

#define ALIGN_BUFFER(p, a) \
    (((uintptr_t)(p) % (a)) ? ((p) + (a) - ((uintptr_t)(p) % (a))) : (p))

static gitm_record *store_next(void) {
    if (g_count == g_cap) {
        size_t ncap = g_cap ? g_cap * 2 : 4096;
        gitm_record *n = (gitm_record *)realloc(g_records, ncap * sizeof(gitm_record));
        if (!n) return NULL;
        g_records = n;
        g_cap = ncap;
    }
    gitm_record *r = &g_records[g_count++];
    memset(r, 0, sizeof(*r));
    return r;
}

static void copy_name(gitm_record *r, const char *name) {
    if (!name) { r->name[0] = '\0'; return; }
    strncpy(r->name, name, NAME_MAX_LEN);
    r->name[NAME_MAX_LEN] = '\0';
}

static void ingest(CUpti_Activity *rec) {
    switch (rec->kind) {
        case CUPTI_ACTIVITY_KIND_KERNEL:
        case CUPTI_ACTIVITY_KIND_CONCURRENT_KERNEL: {
            CUpti_ActivityKernel9 *k = (CUpti_ActivityKernel9 *)rec;
            gitm_record *r = store_next();
            if (!r) return;
            r->kind = REC_KERNEL;
            copy_name(r, k->name);
            r->start_ns = k->start;
            r->end_ns = k->end;
            r->device_id = k->deviceId;
            r->context_id = k->contextId;
            r->stream_id = k->streamId;
            r->correlation_id = k->correlationId;
            r->grid[0] = k->gridX; r->grid[1] = k->gridY; r->grid[2] = k->gridZ;
            r->block[0] = k->blockX; r->block[1] = k->blockY; r->block[2] = k->blockZ;
            r->static_shared_mem = k->staticSharedMemory;
            r->dynamic_shared_mem = k->dynamicSharedMemory;
            r->registers_per_thread = k->registersPerThread;
            break;
        }
        case CUPTI_ACTIVITY_KIND_MEMCPY: {
            CUpti_ActivityMemcpy5 *m = (CUpti_ActivityMemcpy5 *)rec;
            gitm_record *r = store_next();
            if (!r) return;
            r->kind = REC_MEMCPY;
            r->start_ns = m->start;
            r->end_ns = m->end;
            r->device_id = m->deviceId;
            r->context_id = m->contextId;
            r->stream_id = m->streamId;
            r->correlation_id = m->correlationId;
            r->copy_kind = m->copyKind;
            r->bytes = m->bytes;
            break;
        }
        case CUPTI_ACTIVITY_KIND_SYNCHRONIZATION: {
            CUpti_ActivitySynchronization *s = (CUpti_ActivitySynchronization *)rec;
            gitm_record *r = store_next();
            if (!r) return;
            r->kind = REC_SYNC;
            r->start_ns = s->start;
            r->end_ns = s->end;
            r->context_id = s->contextId;
            r->stream_id = s->streamId;
            r->correlation_id = s->correlationId;
            r->sync_type = s->type;
            break;
        }
        default:
            break;  /* kinds GITM doesn't model */
    }
}

static void CUPTIAPI buffer_requested(uint8_t **buffer, size_t *size,
                                      size_t *maxNumRecords) {
    uint8_t *raw = (uint8_t *)malloc(BUF_SIZE + BUF_ALIGN);
    *buffer = (uint8_t *)ALIGN_BUFFER(raw, BUF_ALIGN);
    *size = BUF_SIZE;
    *maxNumRecords = 0;  /* fill as many as fit */
}

static void CUPTIAPI buffer_completed(CUcontext ctx, uint32_t streamId,
                                      uint8_t *buffer, size_t size, size_t validSize) {
    (void)ctx; (void)streamId; (void)size;
    CUpti_Activity *record = NULL;
    pthread_mutex_lock(&g_lock);
    if (validSize > 0) {
        for (;;) {
            CUptiResult st = cuptiActivityGetNextRecord(buffer, validSize, &record);
            if (st == CUPTI_SUCCESS) {
                ingest(record);
            } else if (st == CUPTI_ERROR_MAX_LIMIT_REACHED) {
                break;
            } else {
                break;
            }
        }
    }
    pthread_mutex_unlock(&g_lock);
    free(buffer);  /* matches malloc in buffer_requested (aligned within) */
}

/* ---- Python interface ---- */

static PyObject *set_cupti_error(CUptiResult st, const char *where) {
    const char *msg = NULL;
    cuptiGetResultString(st, &msg);
    PyErr_Format(PyExc_RuntimeError, "CUPTI %s failed: %s", where, msg ? msg : "?");
    return NULL;
}

/* Enable CONCURRENT_KERNEL only, not also CUPTI_ACTIVITY_KIND_KERNEL. Enabling
 * both yields two records per kernel, and the duplicate set comes back with
 * zeroed timestamps (verified on an A100 / CUDA 13). CONCURRENT_KERNEL is the
 * correct kind for async workloads and carries valid start/end. */
static const CUpti_ActivityKind ENABLED_KINDS[] = {
    CUPTI_ACTIVITY_KIND_CONCURRENT_KERNEL,
    CUPTI_ACTIVITY_KIND_MEMCPY,
    CUPTI_ACTIVITY_KIND_SYNCHRONIZATION,
};

static PyObject *py_start(PyObject *self, PyObject *args) {
    (void)self; (void)args;
    if (g_enabled) Py_RETURN_NONE;

    CUptiResult st = cuptiActivityRegisterCallbacks(buffer_requested, buffer_completed);
    if (st != CUPTI_SUCCESS) return set_cupti_error(st, "RegisterCallbacks");

    pthread_mutex_lock(&g_lock);
    g_count = 0;  /* fresh trace */
    pthread_mutex_unlock(&g_lock);

    for (size_t i = 0; i < sizeof(ENABLED_KINDS) / sizeof(ENABLED_KINDS[0]); i++) {
        st = cuptiActivityEnable(ENABLED_KINDS[i]);
        if (st != CUPTI_SUCCESS) return set_cupti_error(st, "Enable");
    }
    g_enabled = 1;
    Py_RETURN_NONE;
}

static PyObject *rec_to_dict(const gitm_record *r) {
    if (r->kind == REC_KERNEL) {
        return Py_BuildValue(
            "{s:s, s:s, s:K, s:K, s:I, s:I, s:I, s:I, s:[iii], s:[iii], s:i, s:i, s:i}",
            "kind", "kernel", "name", r->name,
            "start_ns", (unsigned long long)r->start_ns,
            "end_ns", (unsigned long long)r->end_ns,
            "device_id", r->device_id, "context_id", r->context_id,
            "stream_id", r->stream_id, "correlation_id", r->correlation_id,
            "grid", r->grid[0], r->grid[1], r->grid[2],
            "block", r->block[0], r->block[1], r->block[2],
            "static_shared_mem", r->static_shared_mem,
            "dynamic_shared_mem", r->dynamic_shared_mem,
            "registers_per_thread", r->registers_per_thread);
    } else if (r->kind == REC_MEMCPY) {
        return Py_BuildValue(
            "{s:s, s:i, s:K, s:K, s:K, s:I, s:I, s:I, s:I}",
            "kind", "memcpy", "copy_kind", r->copy_kind,
            "bytes", (unsigned long long)r->bytes,
            "start_ns", (unsigned long long)r->start_ns,
            "end_ns", (unsigned long long)r->end_ns,
            "device_id", r->device_id, "context_id", r->context_id,
            "stream_id", r->stream_id, "correlation_id", r->correlation_id);
    } else {
        return Py_BuildValue(
            "{s:s, s:i, s:K, s:K, s:I, s:I, s:I, s:I}",
            "kind", "sync", "sync_type", r->sync_type,
            "start_ns", (unsigned long long)r->start_ns,
            "end_ns", (unsigned long long)r->end_ns,
            "device_id", r->device_id, "context_id", r->context_id,
            "stream_id", r->stream_id, "correlation_id", r->correlation_id);
    }
}

static PyObject *py_stop(PyObject *self, PyObject *args) {
    (void)self; (void)args;
    if (g_enabled) {
        for (size_t i = 0; i < sizeof(ENABLED_KINDS) / sizeof(ENABLED_KINDS[0]); i++) {
            cuptiActivityDisable(ENABLED_KINDS[i]);
        }
        CUptiResult st = cuptiActivityFlushAll(1 /* FORCE */);
        if (st != CUPTI_SUCCESS) return set_cupti_error(st, "FlushAll");
        g_enabled = 0;
    }

    pthread_mutex_lock(&g_lock);
    PyObject *list = PyList_New((Py_ssize_t)g_count);
    if (!list) { pthread_mutex_unlock(&g_lock); return NULL; }
    for (size_t i = 0; i < g_count; i++) {
        PyObject *d = rec_to_dict(&g_records[i]);
        if (!d) { Py_DECREF(list); pthread_mutex_unlock(&g_lock); return NULL; }
        PyList_SET_ITEM(list, (Py_ssize_t)i, d);  /* steals ref */
    }
    g_count = 0;
    pthread_mutex_unlock(&g_lock);
    return list;
}

static PyObject *py_device_count(PyObject *self, PyObject *args) {
    (void)self; (void)args;
    int n = 0;
    cudaError_t err = cudaGetDeviceCount(&n);
    if (err != cudaSuccess) n = 0;  /* no CUDA devices visible */
    return PyLong_FromLong(n);
}

static PyMethodDef methods[] = {
    {"start", py_start, METH_NOARGS, "Enable CUPTI activity collection."},
    {"stop", py_stop, METH_NOARGS, "Flush and return the record dicts."},
    {"device_count", py_device_count, METH_NOARGS, "Number of CUPTI devices."},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef moddef = {
    PyModuleDef_HEAD_INIT, "_cupti_shim",
    "CUPTI activity collection shim for GITM.", -1, methods,
    NULL, NULL, NULL, NULL,
};

PyMODINIT_FUNC PyInit__cupti_shim(void) {
    return PyModule_Create(&moddef);
}
