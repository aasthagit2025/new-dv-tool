import streamlit as st
import pandas as pd
import numpy as np
import re
import pyreadstat
from collections import Counter

st.title("Automated Data Validation Tool")

# Upload data file
data_file = st.file_uploader("Upload survey data (CSV or SPSS)", type=["csv", "sav"])
rules_file = st.file_uploader("Upload Validation Rules (Excel)", type=["xlsx"])

if data_file and rules_file:
    # Read data
    if data_file.name.endswith(".csv"):
        data = pd.read_csv(data_file)
    else:
        data, meta = pyreadstat.read_sav(data_file)

    # Ensure RespondentID exists
    if "RespondentID" not in data.columns:
        st.error("Dataset must contain a 'RespondentID' column.")
    else:
        rules = pd.ExcelFile(rules_file)
        results = []

        # Iterate through rules
        for sheet in rules.sheet_names:
            rule_df = pd.read_excel(rules, sheet_name=sheet)

            for _, rule in rule_df.iterrows():
                var = str(rule["Variable"])
                check = str(rule["CheckType"]).lower()
                cond = str(rule.get("Condition", ""))

                if var not in data.columns and check != "duplicate":
                    continue

                # ---- MISSING CHECK ----
                if check == "missing":
                    failed = data[data[var].isna()]
                    for rid in failed["RespondentID"]:
                        results.append([rid, var, "Missing", "Value is missing", "Fail"])

                # ---- RANGE CHECK ----
                elif check == "range":
                    min_val, max_val = map(float, cond.split("-"))
                    failed = data[(data[var] < min_val) | (data[var] > max_val)]
                    for rid in failed["RespondentID"]:
                        results.append([rid, var, "Range", f"Not in {cond}", "Fail"])

                # ---- SKIP CHECK ----
                elif check == "skip":
                    dep_var, dep_val = cond.split("=")
                    mask = data[dep_var] != int(dep_val)
                    failed = data[mask & data[var].notna()]
                    for rid in failed["RespondentID"]:
                        results.append([rid, var, "Skip", f"Should be empty if {dep_var}!={dep_val}", "Fail"])

                # ---- MULTI SELECT CHECK ----
                elif check == "multi-select":
                    subset = [c for c in data.columns if c.startswith(var)]
                    for col in subset:
                        invalid = data[~data[col].isin([0, 1])]
                        for rid in invalid["RespondentID"]:
                            results.append([rid, col, "Multi-Select", "Invalid value (not 0/1)", "Fail"])
                    # check at least one =1
                    for i, row in data.iterrows():
                        if row[subset].sum() == 0:
                            results.append([row["RespondentID"], ",".join(subset), "Multi-Select", "No option selected", "Fail"])

                # ---- STRAIGHTLINER CHECK ----
                elif check == "straightliner":
                    subset = [c for c in data.columns if c.startswith(var)]
                    for i, row in data.iterrows():
                        if len(set(row[subset].dropna())) == 1 and len(row[subset].dropna()) > 1:
                            results.append([row["RespondentID"], ",".join(subset), "Straightliner", "All responses same", "Fail"])

                # ---- JUNK OE CHECK ----
                elif check == "junk-oe":
                    pattern = r"[^a-zA-Z\s]"
                    failed = data[data[var].astype(str).str.contains(pattern, regex=True)]
                    for rid in failed["RespondentID"]:
                        results.append([rid, var, "Junk OE", "Contains junk text", "Fail"])

                # ---- AI GENERATED OE CHECK ----
                elif check == "ai-oe":
                    failed = data[data[var].astype(str).str.contains("As an AI", case=False, na=False)]
                    for rid in failed["RespondentID"]:
                        results.append([rid, var, "AI OE", "Likely AI-generated response", "Fail"])

                # ---- DUPLICATE RESPONDENT CHECK ----
                elif check == "duplicate":
                    duplicates = data[data.duplicated("RespondentID", keep=False)]
                    for rid in duplicates["RespondentID"]:
                        results.append([rid, "RespondentID", "Duplicate", "Duplicate RespondentID", "Fail"])

        # Build report
        report_df = pd.DataFrame(results, columns=["RespondentID", "Variable", "CheckType", "Condition", "Issue"])
        st.dataframe(report_df)

        # Download option
        st.download_button("Download Validation Report", report_df.to_excel(index=False), "validation_report.xlsx")
