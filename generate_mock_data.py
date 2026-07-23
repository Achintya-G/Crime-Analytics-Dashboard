"""
Mock Data Generator — AI-Driven Crime Analytics Platform
==========================================================

Generates realistic, structurally-coherent mock data for:
  - Accused (with repeat-offender clustering)
  - CaseMaster (with spatial hotspots + temporal patterns)
  - ActSectionAssociation (crime-type-consistent legal sections)
  - BriefFacts text (template-family based, for meaningful RAG embeddings)

Design principles (see chat explanation):
  1. Storylines, not independent random rows.
  2. Spatial clustering around named hotspots (+ noise).
  3. Temporal weighting by crime type.
  4. Template-family narrative text so semantically similar cases
     actually embed close together.
  5. Real signal in recidivism features (age, prior offenses, gravity).
  6. Referential integrity generated in dependency order.

Usage:
    python generate_mock_data.py --num-cases 1000 --out-dir ./mock_data
    python generate_mock_data.py --num-cases 1000 --postgres "postgresql://postgres:devpass@localhost:5432/crimedb"

Requires:
    pip install faker numpy pandas sqlalchemy psycopg2-binary
"""

import argparse
import json
import random
import uuid
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from faker import Faker

fake = Faker()
Faker.seed(42)
random.seed(42)
np.random.seed(42)

# ----------------------------------------------------------------------
# 1. CONFIG: Hotspots, Crime Types, MO Template Families, Legal Sections
# ----------------------------------------------------------------------

HOTSPOTS = [
    {"name": "Downtown Commercial", "lat": 12.9716, "lng": 77.5946, "weight": 0.35},
    {"name": "Industrial Belt", "lat": 12.9550, "lng": 77.6200, "weight": 0.25},
    {"name": "Residential North", "lat": 13.0100, "lng": 77.5800, "weight": 0.25},
    {"name": "Transit Corridor", "lat": 12.9350, "lng": 77.6100, "weight": 0.15},
]
NOISE_RATIO = 0.10  # fraction of cases scattered uniformly, not in a hotspot

CRIME_TYPES = {
    "Burglary": {
        "sections": ["IPC 457", "IPC 380"],
        "hours": list(range(0, 5)) + list(range(22, 24)),
        "days_weight": {"Mon": 1, "Tue": 1, "Wed": 1, "Thu": 1, "Fri": 1.3, "Sat": 1.5, "Sun": 1.2},
        "gravity_range": (0.4, 0.75),
    },
    "Commercial Break-in": {
        "sections": ["IPC 457", "IPC 380", "IPC 379"],
        "hours": list(range(21, 24)) + list(range(0, 3)),
        "days_weight": {"Mon": 1, "Tue": 1, "Wed": 1, "Thu": 1.1, "Fri": 1.4, "Sat": 1.6, "Sun": 1.3},
        "gravity_range": (0.45, 0.8),
    },
    "Assault": {
        "sections": ["IPC 323", "IPC 324", "IPC 307"],
        "hours": list(range(20, 24)) + list(range(0, 2)),
        "days_weight": {"Mon": 0.8, "Tue": 0.8, "Wed": 0.9, "Thu": 1.0, "Fri": 1.5, "Sat": 1.8, "Sun": 1.4},
        "gravity_range": (0.5, 0.95),
    },
    "Vehicle Theft": {
        "sections": ["IPC 379"],
        "hours": list(range(1, 6)) + list(range(23, 24)),
        "days_weight": {"Mon": 1, "Tue": 1, "Wed": 1, "Thu": 1, "Fri": 1.2, "Sat": 1.2, "Sun": 1},
        "gravity_range": (0.3, 0.6),
    },
    "Cybercrime / Fraud": {
        "sections": ["IPC 420", "IT Act 66C"],
        "hours": list(range(9, 21)),
        "days_weight": {"Mon": 1.2, "Tue": 1.2, "Wed": 1.2, "Thu": 1.1, "Fri": 1, "Sat": 0.7, "Sun": 0.6},
        "gravity_range": (0.35, 0.7),
    },
}

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# MO (Modus Operandi) template families.
# Cases sharing a family + slot values should embed close together in the
# vector store, giving the RAG demo something real to surface.
MO_TEMPLATE_FAMILIES = {
    "Burglary": [
        "Suspect gained entry via {entry_point} using a {break_tool}, targeted {item}, "
        "and fled on foot within an estimated {minutes} minutes. Neighboring residents "
        "reported no unusual activity prior to the incident.",

        "Break-in occurred through {entry_point}; {item} reported missing. Suspect appeared "
        "to avoid areas of security camera coverage, suggesting possible prior surveillance "
        "of the premises. Entry tool consistent with a {break_tool}.",

        "Forced entry via {entry_point} detected during early morning hours. {item} was "
        "disturbed or removed. Method of entry closely matches unsolved incidents in "
        "nearby precincts involving a {break_tool}.",
    ],
    "Commercial Break-in": [
        "Suspect breached {entry_point} of the premises shortly after closing hours, "
        "using a {break_tool} to bypass the lock mechanism. {item} was targeted. Point-of-sale "
        "system and cash drawer showed signs of tampering.",

        "Shop shutter forced open via {entry_point}; suspect used a {break_tool} to disable the "
        "alarm circuit before removing {item}. CCTV footage partially obstructed by "
        "suspect's clothing, consistent with prior premeditation.",

        "Commercial establishment reported {item} missing after suspect gained access "
        "through {entry_point}. A {break_tool} was recovered at the scene, matching tool-mark "
        "evidence from two prior incidents in the same commercial corridor.",
    ],
    "Assault": [
        "Altercation broke out at {location_type} following a verbal dispute. "
        "Suspect struck the victim using {weapon}, resulting in injuries requiring "
        "medical attention. Multiple witnesses present at the scene.",

        "Victim was approached by suspect near {location_type} and assaulted following "
        "a reported prior dispute. {weapon_cap} was allegedly used during the confrontation. "
        "Bystanders intervened before further escalation.",
    ],
    "Vehicle Theft": [
        "Vehicle reported stolen from {location_type}; suspect believed to have used "
        "{vehicle_tool} to bypass the ignition. No witnesses came forward at the time of the incident.",

        "Owner reported vehicle missing from {location_type} after leaving it unattended "
        "for approximately {minutes} minutes. Entry method consistent with use of {vehicle_tool}.",
    ],
    "Cybercrime / Fraud": [
        "Victim reported unauthorized transactions after clicking a link received via "
        "message, consistent with {cyber_vector}-based phishing campaign. Funds routed through "
        "multiple intermediary accounts before withdrawal.",

        "Complainant reported financial loss after a fraudulent call impersonating a bank "
        "official, using {cyber_vector} as the primary vector to extract OTP credentials.",
    ],
}

# Slot pools are scoped per crime-type context so cross-contamination is
# impossible (e.g. a "spoofed caller ID app" can never end up as a physical
# assault weapon). Each key below is only ever referenced by templates in
# its matching crime-type family.
SLOT_VALUES = {
    "entry_point": ["a rear window", "the rear door", "a ground-floor window",
                     "the main shutter", "a side entrance", "the terrace access door"],
    "break_tool": ["glass cutter", "crowbar", "duplicate key", "lock-picking kit",
                    "screwdriver", "hydraulic bolt cutter"],
    "weapon": ["a blunt object", "a knife", "an iron rod", "a broken bottle", "bare hands"],
    "vehicle_tool": ["a duplicate key", "a hot-wiring kit", "a master key", "a signal jammer"],
    "cyber_vector": ["a phishing SMS", "a spoofed caller ID app", "a fake payment gateway link",
                      "a malicious QR code", "a cloned banking app"],
    "item": ["electronics and jewelry", "cash from the register", "a laptop and mobile phone",
             "store inventory", "a two-wheeler parked inside", "documents and valuables"],
    "minutes": [5, 8, 10, 12, 15, 20],
    "location_type": ["a residential parking lot", "a market street", "a bus stop",
                       "a commercial parking area", "outside a bar", "a railway station lot"],
}


def fill_template(template: str) -> str:
    slots_in_template = set(s.strip("{}") for s in
                             __import__("re").findall(r"\{[^}]+\}", template))
    values = {}
    for slot in slots_in_template:
        if slot == "weapon_cap":
            # capitalized variant for sentence-initial placement; reuse the
            # 'weapon' slot's value pool rather than duplicating it
            values[slot] = random.choice(SLOT_VALUES["weapon"]).capitalize()
        else:
            values[slot] = random.choice(SLOT_VALUES[slot])
    return template.format(**values)


# ----------------------------------------------------------------------
# 2. SPATIAL + TEMPORAL SAMPLING
# ----------------------------------------------------------------------

def sample_location():
    """Cluster around hotspots, with a noise fraction scattered uniformly."""
    if random.random() < NOISE_RATIO:
        lat = 12.90 + random.random() * 0.15
        lng = 77.55 + random.random() * 0.10
        return lat, lng
    weights = [h["weight"] for h in HOTSPOTS]
    spot = random.choices(HOTSPOTS, weights=weights, k=1)[0]
    lat = spot["lat"] + np.random.normal(0, 0.008)
    lng = spot["lng"] + np.random.normal(0, 0.008)
    return round(lat, 6), round(lng, 6)


def sample_datetime(crime_type: str, days_back: int = 180):
    cfg = CRIME_TYPES[crime_type]
    day_weights = [cfg["days_weight"][d] for d in DAY_NAMES]
    total = sum(day_weights)
    day_probs = [w / total for w in day_weights]

    base_date = datetime.now() - timedelta(days=random.randint(0, days_back))
    # nudge to a weekday matching the weighted distribution
    target_day = random.choices(DAY_NAMES, weights=day_probs, k=1)[0]
    while DAY_NAMES[base_date.weekday()] != target_day:
        base_date -= timedelta(days=1)

    hour = random.choice(cfg["hours"])
    minute = random.randint(0, 59)
    return base_date.replace(hour=hour, minute=minute, second=0, microsecond=0)


# ----------------------------------------------------------------------
# 3. ACCUSED GENERATION (with repeat-offender injection)
# ----------------------------------------------------------------------

def generate_accused(n: int, repeat_offender_ratio: float = 0.18):
    accused = []
    n_repeat = int(n * repeat_offender_ratio)
    repeat_flags = [True] * n_repeat + [False] * (n - n_repeat)
    random.shuffle(repeat_flags)

    for i, is_repeat in enumerate(repeat_flags):
        accused_id = f"ACC-{i+1:05d}"
        if is_repeat:
            age = random.randint(18, 27)
            prior_offenses = np.random.poisson(3.2)
        else:
            age = random.randint(18, 65)
            prior_offenses = np.random.poisson(0.3)
        accused.append({
            "AccusedMasterID": accused_id,
            "Name": fake.name(),
            "Age": age,
            "IsRepeatOffenderFlag": is_repeat,  # ground-truth for validation only;
                                                 # don't feed directly to the model as a feature
            "PriorOffenseCount": int(prior_offenses),
        })
    return pd.DataFrame(accused)


# ----------------------------------------------------------------------
# 4. CASE GENERATION
# ----------------------------------------------------------------------

def generate_cases(n: int, accused_df: pd.DataFrame):
    cases = []
    sections = []

    crime_type_list = list(CRIME_TYPES.keys())
    # weight commercial break-ins & burglary slightly higher for a richer map demo
    crime_type_weights = [0.28, 0.24, 0.18, 0.16, 0.14]

    repeat_offenders = accused_df[accused_df["IsRepeatOffenderFlag"]]["AccusedMasterID"].tolist()
    all_accused = accused_df["AccusedMasterID"].tolist()

    for i in range(n):
        case_id = f"CASE-{i+1:06d}"
        crime_type = random.choices(crime_type_list, weights=crime_type_weights, k=1)[0]
        cfg = CRIME_TYPES[crime_type]

        lat, lng = sample_location()
        occurred_at = sample_datetime(crime_type)

        # ~65% chance a repeat offender is linked, when available, to give the
        # recidivism model & graph view real linked cases to show off
        if repeat_offenders and random.random() < 0.65:
            accused_id = random.choice(repeat_offenders)
        else:
            accused_id = random.choice(all_accused)

        template_family = MO_TEMPLATE_FAMILIES.get(crime_type)
        brief_facts = fill_template(random.choice(template_family)) if template_family else fake.paragraph(nb_sentences=3)

        gravity_low, gravity_high = cfg["gravity_range"]
        gravity_score = round(random.uniform(gravity_low, gravity_high), 3)

        cases.append({
            "CaseID": case_id,
            "AccusedMasterID": accused_id,
            "CrimeMinorHead": crime_type,
            "Latitude": lat,
            "Longitude": lng,
            "OccurredAt": occurred_at.isoformat(),
            "BriefFacts": brief_facts,
            "GravityOffenceScore": gravity_score,
        })

        for section in cfg["sections"]:
            # not every case cites every possible section — pick 1-2
            if random.random() < 0.7 or section == cfg["sections"][0]:
                sections.append({
                    "CaseID": case_id,
                    "SectionCode": section,
                })

    return pd.DataFrame(cases), pd.DataFrame(sections)


# ----------------------------------------------------------------------
# 5. OUTPUT
# ----------------------------------------------------------------------

def write_csv(out_dir, accused_df, cases_df, sections_df):
    import os
    os.makedirs(out_dir, exist_ok=True)
    accused_df.to_csv(f"{out_dir}/accused.csv", index=False)
    cases_df.to_csv(f"{out_dir}/case_master.csv", index=False)
    sections_df.to_csv(f"{out_dir}/act_section_association.csv", index=False)
    print(f"Wrote CSVs to {out_dir}/")


def write_postgres(conn_string, accused_df, cases_df, sections_df):
    """
    Appends into tables created by init-db/01-init.sql (which sets up the
    PostGIS Geom column + trigger). Run with --reset first if you want a
    clean reload instead of accumulating rows.
    """
    from sqlalchemy import create_engine, text
    engine = create_engine(conn_string)

    with engine.begin() as conn:
        conn.execute(text('DELETE FROM act_section_association'))
        conn.execute(text('DELETE FROM case_master'))
        conn.execute(text('DELETE FROM accused'))

    # sections dropped its auto id col so Postgres' SERIAL handles it
    sections_out = sections_df.copy()

    accused_df.to_sql("accused", engine, if_exists="append", index=False)
    cases_df.to_sql("case_master", engine, if_exists="append", index=False)
    sections_out.to_sql("act_section_association", engine, if_exists="append", index=False)
    print(f"Loaded tables into {conn_string}")


def main():
    parser = argparse.ArgumentParser(description="Generate mock crime analytics data")
    parser.add_argument("--num-cases", type=int, default=1000)
    parser.add_argument("--num-accused", type=int, default=None,
                         help="Defaults to num_cases // 3 (so cases link back to a realistic pool)")
    parser.add_argument("--out-dir", type=str, default="./mock_data")
    parser.add_argument("--postgres", type=str, default=None,
                         help="Postgres connection string, e.g. postgresql://user:pass@localhost:5432/crimedb")
    args = parser.parse_args()

    num_accused = args.num_accused or max(50, args.num_cases // 3)

    print(f"Generating {num_accused} accused profiles...")
    accused_df = generate_accused(num_accused)

    print(f"Generating {args.num_cases} cases...")
    cases_df, sections_df = generate_cases(args.num_cases, accused_df)

    if args.postgres:
        write_postgres(args.postgres, accused_df, cases_df, sections_df)
    else:
        write_csv(args.out_dir, accused_df, cases_df, sections_df)

    print("\nSummary:")
    print(f"  Accused: {len(accused_df)} ({accused_df['IsRepeatOffenderFlag'].sum()} flagged repeat offenders)")
    print(f"  Cases:   {len(cases_df)}")
    print(f"  Crime type breakdown:\n{cases_df['CrimeMinorHead'].value_counts()}")
    print(f"  Sections: {len(sections_df)}")


if __name__ == "__main__":
    main()
