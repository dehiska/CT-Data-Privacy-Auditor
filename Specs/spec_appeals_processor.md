# Agent Spec: Appeals Processor

import pandas as pd

def has_appeal(policy):
    keywords = ["appeal", "dispute", "review decision"]
    return any(k in policy.lower() for k in keywords)

def check_timeline(df):
    df["days"] = pd.to_datetime(df["response"]) - pd.to_datetime(df["request"])
    return df[df["days"].dt.days > 45].shape[0]

def appeals_processor_agent(state):
    policy = state.get("business_policy", "")

    violations = []

    if not has_appeal(policy):
        violations.append("CRITICAL_NO_APPEAL")

    if "request_log" in state:
        df = pd.read_csv(state["request_log"])
        late = check_timeline(df)
        if late > 0:
            violations.append("LATE_RESPONSE")

    state["appeals"] = {
        "violations": violations,
        "risk": "High" if violations else "Low"
    }

    return state