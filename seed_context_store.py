#!/usr/bin/env python3
"""
Seed script for gitm-context-store Airtable tables.
Run with: python3 seed_context_store.py
Requires AIRTABLE_API_KEY and AIRTABLE_BASE_ID in environment.
"""

import os
import json
import urllib.request
import urllib.error

BASE_ID = "appi400mk6PHDF6Ex"
API_KEY = os.environ.get("AIRTABLE_API_KEY")

if not API_KEY:
    print("ERROR: AIRTABLE_API_KEY not found in environment. Run: source ~/.hermes/.env")
    exit(1)

def post_record(table, fields):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table}"
    data = json.dumps({"fields": fields}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {API_KEY}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            print(f"  OK: {table} — {list(fields.values())[0]}")
            return result
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  ERROR: {table} — {list(fields.values())[0]} — {body}")
        return None

# ─── context_voice_rules ───────────────────────────────────────────────────

print("\nSeeding context_voice_rules...")

voice_rules = [
    {
        "rule_id": "voice_002",
        "category": "tone",
        "rule": "Lead with output, not cost. Buyers want more capacity, not a lower bill.",
        "example_good": "Run more workloads on the hardware you have.",
        "example_bad": "Reduce your GPU spend by up to 30%.",
        "applies_to": ["all"]
    },
    {
        "rule_id": "voice_003",
        "category": "language",
        "rule": "Never call Git.M a profiler, scheduler, or monitoring tool. Break the pattern match immediately.",
        "example_good": "Unlike profilers that describe what happened, we prescribe and apply fixes.",
        "example_bad": "Git.M is a GPU optimization and monitoring platform.",
        "applies_to": ["all"]
    },
    {
        "rule_id": "voice_004",
        "category": "structure",
        "rule": "One ask per message. No feature lists. No bullet points in cold outreach.",
        "example_good": "Single clear CTA at the end.",
        "example_bad": "Three bullet points listing product features mid-message.",
        "applies_to": ["linkedin", "email"]
    },
    {
        "rule_id": "voice_005",
        "category": "anti_pattern",
        "rule": "Never use utilize, leverage, synergy, streamline, or innovative.",
        "example_good": "We find where your workload loses capacity and fix it.",
        "example_bad": "We leverage innovative techniques to streamline GPU utilization.",
        "applies_to": ["all"]
    },
    {
        "rule_id": "voice_006",
        "category": "tone",
        "rule": "Peer-curious register for intern senders. Humble, direct, no sales language.",
        "example_good": "I'm a Berkeley student studying GPU runtime inefficiency — your work at [company] is exactly the kind of system I'm trying to understand.",
        "example_bad": "Hi, I wanted to reach out about an exciting opportunity to optimize your GPU infrastructure.",
        "applies_to": ["linkedin"]
    },
    {
        "rule_id": "voice_007",
        "category": "language",
        "rule": "Capacity, not cost. Recovered capacity is the value. Cost reduction is downstream.",
        "example_good": "More of your GPU ceiling doing useful work.",
        "example_bad": "Save money on your GPU bill.",
        "applies_to": ["all"]
    },
    {
        "rule_id": "voice_008",
        "category": "anti_pattern",
        "rule": "No generic openers. Never start with Hope this finds you well or I came across your profile.",
        "example_good": "Start with a specific observation or credibility anchor.",
        "example_bad": "Hope this finds you well! I came across your profile and was impressed by your work.",
        "applies_to": ["linkedin", "email"]
    },
]

for rule in voice_rules:
    post_record("context_voice_rules", rule)

# ─── context_sender_personas ───────────────────────────────────────────────

print("\nSeeding context_sender_personas...")

personas = [
    {
        "sender_id": "asmar",
        "full_name": "Asmar Khasmammadli",
        "role": "GTM Intern",
        "school": "UC Berkeley",
        "background": "UC Berkeley student studying GPU runtime systems with direct access to Git.M engineering team and early findings.",
        "voice_register": "peer-curious",
        "credibility_anchor": "UC Berkeley student studying GPU runtime systems. Direct access to Git.M's engineering team and early findings.",
        "tone_notes": "Humble and curious. Reaches out to learn, not to sell. Never pitches.",
        "active": True
    },
    {
        "sender_id": "jane",
        "full_name": "Jane",
        "role": "GTM Intern",
        "school": "UC Berkeley",
        "background": "UC Berkeley student studying how GPU-intensive teams handle performance gaps.",
        "voice_register": "peer-curious",
        "credibility_anchor": "UC Berkeley student. Research framing — studying how GPU-intensive teams handle performance gaps.",
        "tone_notes": "Slightly more research-oriented. Can lead with a study framing.",
        "active": True
    },
    {
        "sender_id": "giancarlos",
        "full_name": "Giancarlos",
        "role": "GTM Intern",
        "school": "UC Berkeley",
        "background": "UC Berkeley student with interest in ML systems and HPC workloads.",
        "voice_register": "peer-curious",
        "credibility_anchor": "UC Berkeley student with interest in ML systems and HPC workloads.",
        "tone_notes": "Can lean more technical with HPC and scientific compute prospects.",
        "active": True
    },
    {
        "sender_id": "jalon",
        "full_name": "Jalon",
        "role": "Founder",
        "school": "UVA",
        "background": "Founded Git.M. Built the runtime optimization layer. Deep technical credibility across GPU workloads.",
        "voice_register": "founder",
        "credibility_anchor": "Founded Git.M. Built the runtime optimization layer. Deep technical credibility across GPU workloads.",
        "tone_notes": "Direct, peer-to-peer, no fluff. Founder-to-founder or founder-to-CTO. Short messages.",
        "active": False
    },
    {
        "sender_id": "adit",
        "full_name": "Adit",
        "role": "Founder",
        "school": "",
        "background": "Co-founder. Technical and commercial credibility. Prior network includes PubMatic, Intuit, Oracle.",
        "voice_register": "founder",
        "credibility_anchor": "Co-founder. Technical and commercial credibility.",
        "tone_notes": "Similar to Jalon. Peer register with senior buyers.",
        "active": False
    },
    {
        "sender_id": "evan",
        "full_name": "Evan",
        "role": "Advisor/Team",
        "school": "",
        "background": "Deep systems background. Hybrid FDE covering multimodal, robotics, world models.",
        "voice_register": "technical-peer",
        "credibility_anchor": "Deep systems background.",
        "tone_notes": "Technical peer register. Use for highly technical prospects.",
        "active": True
    },
]

for persona in personas:
    post_record("context_sender_personas", persona)

# ─── context_copy_variants ─────────────────────────────────────────────────

print("\nSeeding context_copy_variants...")

variants = [
    {
        "variant_id": "v0_pick_your_brain",
        "variant_name": "Pick your brain",
        "opener_style": "student-credibility",
        "hook_type": "curiosity-flattery",
        "cta": "15-min-soft",
        "voice_register": "peer-curious",
        "signal_reference_style": "none",
        "body_template": "Hi {first_name}, I'm a student at UC Berkeley studying how {vertical} teams manage GPU runtime inefficiency. Your work at {company} is exactly the kind of system I'm trying to understand better. Would you be open to 15 minutes? I'd love to hear how your team thinks about this.",
        "sender_id": "asmar",
        "vertical": "global",
        "status": "active",
    },
    {
        "variant_id": "v0_industry_study",
        "variant_name": "Industry study",
        "opener_style": "student-credibility",
        "hook_type": "research-framing",
        "cta": "15-min-soft",
        "voice_register": "peer-curious",
        "signal_reference_style": "none",
        "body_template": "Hi {first_name}, I'm running a small study at Berkeley on how {vertical} teams handle GPU performance gaps. Happy to share aggregated findings afterward. Would you be open to 15 minutes to share your experience?",
        "sender_id": "jane",
        "vertical": "global",
        "status": "active",
    },
    {
        "variant_id": "v0_sanity_check",
        "variant_name": "Sanity-check my read",
        "opener_style": "student-credibility",
        "hook_type": "hypothesis-validation",
        "cta": "15-min-or-reply",
        "voice_register": "peer-curious",
        "signal_reference_style": "hypothesis-direct",
        "body_template": "Hi {first_name}, I'm a Berkeley student looking at GPU runtime inefficiency in {vertical} workloads. My read is that {failure_mode} is one of the harder gaps to close with existing tools — curious if that matches what you see. Worth a 15-minute call, or happy to hear your take in a reply.",
        "sender_id": "giancarlos",
        "vertical": "global",
        "status": "active",
    },
]

for variant in variants:
    post_record("context_copy_variants", variant)

# ─── context_product_state ─────────────────────────────────────────────────

print("\nSeeding context_product_state...")

product_state = [
    {"field_id": "product_001", "category": "positioning", "label": "What Git.M is", "content": "Runtime software that models how a GPU workload should execute, detects where the real runtime path loses productive capacity, proves which fixes recover it, and safely applies those fixes over time.", "source": "arch_doc"},
    {"field_id": "product_002", "category": "positioning", "label": "What Git.M is NOT", "content": "Not a profiler. Not a scheduler. Not a kernel optimizer. Not an inference framework. Not a monitoring tool.", "source": "gtm_brief"},
    {"field_id": "product_003", "category": "icp", "label": "ICP Phase 1", "content": "Multi-tenant GPU platforms, HPC platforms, managed GPU clouds, sovereign compute providers. Route: SDK embed inside their offering.", "source": "gtm_brief"},
    {"field_id": "product_004", "category": "icp", "label": "ICP Phase 2", "content": "Mid-market companies running non-text GPU workloads: biotech, robotics, autonomous systems, HPC, defense, research labs.", "source": "gtm_brief"},
    {"field_id": "product_005", "category": "differentiator", "label": "vs profilers", "content": "Profilers describe what happened. Git.M prescribes and applies fixes.", "source": "gtm_brief"},
    {"field_id": "product_006", "category": "differentiator", "label": "vs inference frameworks", "content": "vLLM and TensorRT are LLM-specific. Git.M works across all GPU workloads.", "source": "gtm_brief"},
    {"field_id": "product_007", "category": "differentiator", "label": "vs orchestrators", "content": "Kubernetes and Slurm decide where workloads run. Git.M optimizes execution inside the cluster. Phase 1 partners, not competitors.", "source": "gtm_brief"},
    {"field_id": "product_008", "category": "not_this", "label": "Why not pure LLM serving yet", "content": "Mature tooling (vLLM, TensorRT, SGLang) and established benchmarks. Need proof before entering.", "source": "gtm_brief"},
    {"field_id": "product_009", "category": "positioning", "label": "Value statement", "content": "Capacity, not cost. More of the GPU ceiling doing useful work.", "source": "gtm_brief"},
    {"field_id": "product_010", "category": "icp", "label": "Buyer persona", "content": "VP/Head of Infrastructure, VP/Head of ML Platform, Director of ML Engineering, CTO at smaller companies, PIs and lab leadership at research orgs.", "source": "gtm_brief"},
]

for item in product_state:
    post_record("context_product_state", item)

# ─── context_objection_responses ──────────────────────────────────────────

print("\nSeeding context_objection_responses...")

objections = [
    {"objection_id": "obj_001", "objection": "We already use Nsight / PyTorch Profiler.", "category": "competitor", "response": "Profilers describe what happened. Git.M diagnoses why and applies the fix. Profilers require a human to interpret results and implement changes. Git.M closes the loop automatically.", "compare_to": "Nsight"},
    {"objection_id": "obj_002", "objection": "We use vLLM / TensorRT for inference.", "category": "competitor", "response": "Git.M is not an inference framework. We work at the runtime layer underneath — across training, inference, and scientific compute. vLLM and Git.M are not in conflict.", "compare_to": "vLLM"},
    {"objection_id": "obj_003", "objection": "We use Datadog / Grafana for GPU monitoring.", "category": "competitor", "response": "Monitoring surfaces symptoms. Git.M acts on causes. We don't replace your observability stack — we sit underneath it and close the gaps it can't act on.", "compare_to": "Datadog"},
    {"objection_id": "obj_004", "objection": "We don't have GPU performance problems.", "category": "trust", "response": "Every GPU workload operates below its attainable ceiling. The gap is usually invisible to existing tools because they don't model what the workload should achieve. We find what's invisible.", "compare_to": ""},
    {"objection_id": "obj_005", "objection": "We have an internal perf team.", "category": "scope", "response": "Internal perf teams focus on kernel-level optimization and profiling. The runtime path — scheduling, memory movement, contention, sync — is where most of the remaining gap lives, and it's where existing tooling doesn't reach.", "compare_to": ""},
]

for obj in objections:
    post_record("context_objection_responses", obj)

print("\nDone. All tables seeded.")
EOF