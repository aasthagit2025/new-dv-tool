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
    if data_file.name.endswith(".csv"):
        df = pd.read_csv(data_file)
    elif data_file.name.endswith(".xlsx"):
        df = pd.read_excel(data_file)
    elif data_file.name.endswith(".sav"):
        df, meta = pyreadstat.read_sav(data_file)
    else:
        st.error("Unsupported file type")
        st.stop()

    # --- Load Rules ---
    rules_df = pd.read_excel(rules_file)

    # --- Validation Report Logic (simplified example) ---
    report = []
    for _, rule in rules_df.iterrows():
        q = rule["Question"]
        check_type = rule["Check_Type"]
        condition = rule["Condition"]

        if q not in df.columns:
            report.append({"Question": q, "Check_Type": check_type, "Issue": "Question not found in dataset"})
            continue

        if check_type == "Missing":
            missing = df[q].isna().sum()
            if missing > 0:
                report.append({"Question": q, "Check_Type": "Missing", "Issue": f"{missing} missing values"})

        elif check_type == "Range":
            try:
                min_val, max_val = map(int, condition.split("-"))
                out_of_range = df[~df[q].between(min_val, max_val)].shape[0]
                if out_of_range > 0:
                    report.append({"Question": q, "Check_Type": "Range", "Issue": f"{out_of_range} out-of-range values"})
            except:
                report.append({"Question": q, "Check_Type": "Range", "Issue": "Invalid range condition"})

        elif check_type == "Skip":
            # Example: "If Q1=2 then Q3 should be empty"
            try:
                cond_parts = condition.split("then")
                if_part, then_part = cond_parts[0].strip(), cond_parts[1].strip()
                if_q, if_val = if_part.replace("If", "").strip().split("=")
                then_q = then_part.split()[0]
                subset = df[df[if_q.strip()] == int(if_val.strip())]
                invalid = subset[then_q].notna().sum()
                if invalid > 0:
                    report.append({"Question": q, "Check_Type": "Skip", "Issue": f"{invalid} invalid skip logic cases"})
            except:
                report.append({"Question": q, "Check_Type": "Skip", "Issue": "Invalid skip rule format"})

        elif check_type == "Multi-Select":
            # Example rule: "Only 0/1 allowed; Sum across Q4_1-Q4_5 >= 1"
            related_cols = [col for col in df.columns if col.startswith(q)]
            for col in related_cols:
                invalid = df[~df[col].isin([0, 1])].shape[0]
                if invalid > 0:
                    report.append({"Question": col, "Check_Type": "Multi-Select", "Issue": f"{invalid} invalid values (not 0/1)"})
            if len(related_cols) > 0:
                zero_sum = (df[related_cols].sum(axis=1) == 0).sum()
                if zero_sum > 0:
                    report.append({"Question": q, "Check_Type": "Multi-Select", "Issue": f"{zero_sum} respondents selected none"})

        elif check_type == "Straightliner":
            related_cols = [col for col in df.columns if col.startswith(q)]
            if len(related_cols) > 1:
                straightliners = df[related_cols].nunique(axis=1)
                count = (straightliners == 1).sum()
                if count > 0:
                    report.append({"Question": q, "Check_Type": "Straightliner", "Issue": f"{count} straightliner responses"})

        elif check_type == "OpenEnd_Junk":
            junk = df[q].astype(str).str.len() < 3
            junk_count = junk.sum()
            if junk_count > 0:
                report.append({"Question": q, "Check_Type": "OpenEnd_Junk", "Issue": f"{junk_count} junk/short responses"})

        elif check_type == "Duplicate":
            if q in df.columns:
                duplicate_count = df.duplicated(subset=[q]).sum()
                if duplicate_count > 0:
                    report.append({"Question": q, "Check_Type": "Duplicate", "Issue": f"{duplicate_count} duplicate IDs"})

    report_df = pd.DataFrame(report)

    st.write("### Validation Report")
    st.dataframe(report_df)

    # --- Download Report ---
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        report_df.to_excel(writer, index=False, sheet_name="Validation Report")
    st.download_button("Download Validation Report", output.getvalue(), "validation_report.xlsx")
