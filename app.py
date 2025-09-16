import streamlit as st
import pandas as pd
import pyreadstat
import io

st.title("Survey Data Validation Tool")

# --- File Upload ---
data_file = st.file_uploader("Upload your survey data file (CSV, Excel, or SPSS)", type=["csv", "xlsx", "sav"])
rules_file = st.file_uploader("Upload validation rules (Excel)", type=["xlsx"])

if data_file and rules_file:
    # --- Load Data ---
    name = data_file.name.lower()
    if name.endswith(".csv"):
        df = pd.read_csv(data_file)
    elif name.endswith(".xlsx") or name.endswith(".xls"):
        df = pd.read_excel(data_file)
    elif name.endswith(".sav"):
        df, meta = pyreadstat.read_sav(data_file)
    else:
        st.error("Unsupported file type")
        st.stop()

    # Ensure RespondentID exists so we can report respondent-level issues
    if "RespondentID" not in df.columns:
        df.insert(0, "RespondentID", range(1, len(df) + 1))

    # --- Load Rules ---
    rules_df = pd.read_excel(rules_file)

    # --- Validation Report Logic (per-respondent detail) ---
    rows = []  # will hold dicts with RespondentID, Question, Check_Type, Issue, Value

    for _, rule in rules_df.iterrows():
        q = rule["Question"]
        check_type = rule["Check_Type"]
        condition = str(rule.get("Condition", "")).strip()

        # If question not present in dataset -> dataset-level note
        if q not in df.columns:
            rows.append({
                "RespondentID": "",
                "Question": q,
                "Check_Type": check_type,
                "Issue": "Question not found in dataset",
                "Value": ""
            })
            continue

        # --- Missing: list each respondent with missing value ---
        if check_type == "Missing":
            mask = df[q].isna()
            for idx in df[mask].index:
                rows.append({
                    "RespondentID": df.at[idx, "RespondentID"],
                    "Question": q,
                    "Check_Type": "Missing",
                    "Issue": "Value is missing",
                    "Value": df.at[idx, q]
                })

        # --- Range: list each respondent out of range or non-numeric ---
        elif check_type == "Range":
            try:
                parts = [p.strip() for p in condition.split("-")]
                min_val = float(parts[0])
                max_val = float(parts[1])
            except Exception:
                # If range parse fails, add a dataset-level error
                rows.append({
                    "RespondentID": "",
                    "Question": q,
                    "Check_Type": "Range",
                    "Issue": f"Invalid range condition '{condition}'",
                    "Value": ""
                })
                continue

            # numeric coercion to catch non-numeric values
            numeric_series = pd.to_numeric(df[q], errors="coerce")
            non_numeric_mask = df[q].notna() & numeric_series.isna()
            for idx in df[non_numeric_mask].index:
                rows.append({
                    "RespondentID": df.at[idx, "RespondentID"],
                    "Question": q,
                    "Check_Type": "Range",
                    "Issue": "Non-numeric value",
                    "Value": df.at[idx, q]
                })
            out_of_range_mask = numeric_series.notna() & ~numeric_series.between(min_val, max_val)
            for idx in df[out_of_range_mask].index:
                rows.append({
                    "RespondentID": df.at[idx, "RespondentID"],
                    "Question": q,
                    "Check_Type": "Range",
                    "Issue": f"Value out of range ({min_val}-{max_val})",
                    "Value": df.at[idx, q]
                })

        # --- Skip: Example format "If Q1=2 then Q3 should be empty" ---
        elif check_type == "Skip":
            try:
                # split by 'then' to handle formats like "If Q1=2 then Q3 should be empty"
                cond_parts = condition.split("then")
                if_part = cond_parts[0].strip()
                then_part = cond_parts[1].strip()
                if_q, if_val = if_part.replace("If", "").strip().split("=")
                then_q = then_part.split()[0]
                if_q = if_q.strip()
                if_val = if_val.strip()

                # subset where condition holds
                subset_mask = df[if_q] == pd.to_numeric(if_val, errors="coerce")
                # respondents who violated skip (i.e., then_q is NOT blank)
                violate_mask = subset_mask & df[then_q].notna() & (df[then_q].astype(str).str.strip() != "")
                for idx in df[violate_mask].index:
                    rows.append({
                        "RespondentID": df.at[idx, "RespondentID"],
                        "Question": then_q,
                        "Check_Type": "Skip",
                        "Issue": f"Answered but should be blank when {if_q}={if_val}",
                        "Value": df.at[idx, then_q]
                    })
            except Exception:
                rows.append({
                    "RespondentID": "",
                    "Question": q,
                    "Check_Type": "Skip",
                    "Issue": "Invalid skip rule format",
                    "Value": condition
                })

        # --- Multi-Select: related columns start with q (prefix) ---
        elif check_type == "Multi-Select":
            related_cols = [col for col in df.columns if col.startswith(q)]
            # invalid values (not 0/1)
            for col in related_cols:
                mask_invalid = df[col].notna() & (~df[col].isin([0, 1]))
                for idx in df[mask_invalid].index:
                    rows.append({
                        "RespondentID": df.at[idx, "RespondentID"],
                        "Question": col,
                        "Check_Type": "Multi-Select",
                        "Issue": "Invalid value (not 0/1)",
                        "Value": df.at[idx, col]
                    })
            # none selected: sum across related cols == 0 (treat NaN as 0)
            if related_cols:
                sums = df[related_cols].fillna(0).sum(axis=1)
                mask_none = sums == 0
                for idx in df[mask_none].index:
                    rows.append({
                        "RespondentID": df.at[idx, "RespondentID"],
                        "Question": q,
                        "Check_Type": "Multi-Select",
                        "Issue": "No options selected in multiselect group",
                        "Value": ", ".join([str(df.at[idx, c]) for c in related_cols])
                    })

        # --- Straightliner: related columns start with q (prefix) ---
        elif check_type == "Straightliner":
            related_cols = [col for col in df.columns if col.startswith(q)]
            if len(related_cols) > 1:
                for idx in df.index:
                    vals = df.loc[idx, related_cols].dropna().astype(str).str.strip().tolist()
                    if len(vals) > 1 and len(set(vals)) == 1:
                        rows.append({
                            "RespondentID": df.at[idx, "RespondentID"],
                            "Question": ",".join(related_cols),
                            "Check_Type": "Straightliner",
                            "Issue": "All responses identical across the block",
                            "Value": vals[0] if vals else ""
                        })

        # --- OpenEnd_Junk: short / gibberish (simple heuristic) ---
        elif check_type == "OpenEnd_Junk":
            # treat strings of length <3 or common junk markers as junk
            s = df[q].astype(str).fillna("")
            mask_short = s.str.len() < 3
            mask_lorem = s.str.lower().str.contains("lorem", na=False)
            mask_asd = s.str.lower().str.contains("asd|qwer|asdf", na=False)
            mask = (mask_short | mask_lorem | mask_asd) & (s != "nan")
            for idx in df[mask].index:
                rows.append({
                    "RespondentID": df.at[idx, "RespondentID"],
                    "Question": q,
                    "Check_Type": "OpenEnd_Junk",
                    "Issue": "Open-end looks like junk/low-effort",
                    "Value": df.at[idx, q]
                })

        # --- Duplicate: report each respondent who is duplicated on this variable ---
        elif check_type == "Duplicate":
            if q in df.columns:
                dup_df = df[df.duplicated(subset=[q], keep=False)]
                for idx in dup_df.index:
                    rows.append({
                        "RespondentID": df.at[idx, "RespondentID"],
                        "Question": q,
                        "Check_Type": "Duplicate",
                        "Issue": f"Duplicate value ({df.at[idx, q]})",
                        "Value": df.at[idx, q]
                    })

        else:
            # unknown check type -> note it at dataset level
            rows.append({
                "RespondentID": "",
                "Question": q,
                "Check_Type": check_type,
                "Issue": "Unknown check type (no evaluation)",
                "Value": condition
            })

    # Build report DataFrame
    report_df = pd.DataFrame(rows, columns=["RespondentID", "Question", "Check_Type", "Issue", "Value"])

    st.write("### Validation Report (detailed by Respondent)")
    st.dataframe(report_df)

    # --- Download using openpyxl (works on Streamlit Cloud) ---
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        report_df.to_excel(writer, index=False, sheet_name="Validation Report")
    output.seek(0)

    st.download_button(
        label="Download Validation Report",
        data=output.getvalue(),
        file_name="validation_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
