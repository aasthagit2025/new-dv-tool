import streamlit as st
import pandas as pd
import numpy as np
import pyreadstat
import io
import re

st.title("📊 Survey Data Validation Tool")

# --- Upload data ---
data_file = st.file_uploader("Upload survey data (CSV or SAV)", type=["csv", "sav"])
rules_file = st.file_uploader("Upload validation rules (Excel)", type=["xlsx"])

if data_file and rules_file:
    # --- Read data ---
    if data_file.name.endswith(".csv"):
        try:
            data = pd.read_csv(data_file)
        except Exception:
            data = pd.read_csv(data_file, encoding="latin1", on_bad_lines="skip")
    else:
        df, meta = pyreadstat.read_sav(data_file)
        data = df.copy()

    # Ensure RespondentID exists
    if "RespondentID" not in data.columns:
        data.insert(0, "RespondentID", range(1, len(data) + 1))

    # --- Read rules ---
    rules = pd.read_excel(rules_file)

    results = []

    # --- Apply validation rules ---
    for _, rule in rules.iterrows():
        var = rule["Variable"]
        check = rule["CheckType"].lower()
        cond = str(rule["Condition"]).strip()

        # Missing check
        if check == "missing":
            failed = data[data[var].isna()]
            for rid in failed["RespondentID"]:
                results.append([rid, var, "Missing", "Value is missing", "Fail"])

        # Range check
        elif check == "range":
            if "-" in cond:
                min_v, max_v = cond.split("-")
                min_v, max_v = float(min_v), float(max_v)
                failed = data[(data[var] < min_v) | (data[var] > max_v)]
                for rid in failed["RespondentID"]:
                    results.append([rid, var, "Range", f"Valid range {min_v}-{max_v}", "Fail"])

        # Skip check
        elif check == "skip":
            if "=" in cond:
                dep_var, dep_val = cond.split("=")
                dep_val = dep_val.strip()
                mask = (data[dep_var] == float(dep_val)) & (data[var].isna())
                failed = data[mask]
                for rid in failed["RespondentID"]:
                    results.append([rid, var, "Skip", f"Should not skip when {dep_var}={dep_val}", "Fail"])

        # Multi-select
        elif check == "multi-select":
            multi_vars = [c for c in data.columns if c.startswith("Multi_")]
            for v in multi_vars:
                failed = data[~data[v].isin([0, 1])]
                for rid in failed["RespondentID"]:
                    results.append([rid, v, "Multi-Select", "Only 0/1 allowed", "Fail"])
            failed_sum = data[data[multi_vars].sum(axis=1) == 0]
            for rid in failed_sum["RespondentID"]:
                results.append([rid, ",".join(multi_vars), "Multi-Select", "At least one=1 required", "Fail"])

        # Straightliners
        elif check == "straightliner":
            straight_vars = [c for c in data.columns if c.startswith(var)]
            failed = data[straight_vars][data[straight_vars].nunique(axis=1) == 1]
            for rid in data.loc[failed.index, "RespondentID"]:
                results.append([rid, ",".join(straight_vars), "Straightliner", "All answers identical", "Fail"])

        # Junk OE
        elif check == "junk-oe":
            failed = data[data[var].astype(str).str.contains(r"^[^a-zA-Z0-9]+$", na=False)]
            for rid in failed["RespondentID"]:
                results.append([rid, var, "Junk-OE", "Gibberish open-end", "Fail"])

        # AI OE
        elif check == "ai-oe":
            ai_patterns = ["as an ai", "language model", "cannot provide"]
            failed = data[data[var].astype(str).str.lower().str.contains("|".join(ai_patterns), na=False)]
            for rid in failed["RespondentID"]:
                results.append([rid, var, "AI-OE", "Possible AI-generated response", "Fail"])

        # Duplicate RespondentID
        elif check == "duplicate":
            dupes = data[data.duplicated("RespondentID", keep=False)]
            for rid in dupes["RespondentID"]:
                results.append([rid, "RespondentID", "Duplicate", "Duplicate RespondentID", "Fail"])

    # --- Build final report ---
    report_df = pd.DataFrame(results, columns=["RespondentID", "Variable", "CheckType", "Condition", "Issue"])

    st.subheader("Validation Results")
    st.dataframe(report_df)

    # --- Download button (FIXED) ---
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        report_df.to_excel(writer, index=False, sheet_name="Validation Report")
    output.seek(0)

    st.download_button(
        label="Download Validation Report",
        data=output,
        file_name="validation_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
