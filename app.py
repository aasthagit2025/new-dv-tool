import streamlit as st
import pandas as pd
import numpy as np
import io

# File upload
st.title("Data Validation Tool")

uploaded_file = st.file_uploader("Upload your data file", type=["csv", "xlsx", "sav"])

if uploaded_file:
    file_ext = uploaded_file.name.split(".")[-1].lower()

    if file_ext == "csv":
        df = pd.read_csv(uploaded_file)
    elif file_ext == "xlsx":
        df = pd.read_excel(uploaded_file)
    elif file_ext == "sav":
        import pyreadstat
        df, meta = pyreadstat.read_sav(uploaded_file)
    else:
        st.error("Unsupported file type")
        st.stop()

    st.write("Data Preview:", df.head())

    # Ensure RespondentID exists
    if "RespondentID" not in df.columns:
        df.insert(0, "RespondentID", range(1, len(df) + 1))

    # Validation rules (example rules — extend as needed)
    rules = [
        {"rule": "Missing Values", "check": lambda d: d.isnull()},
        {"rule": "Negative Values", "check": lambda d: d < 0},
    ]

    # Validation process
    issues = []
    for col in df.columns:
        if col == "RespondentID":
            continue
        for rule in rules:
            mask = rule["check"](df[col])
            if mask.any():
                for idx in df[mask].index:
                    issues.append({
                        "RespondentID": df.at[idx, "RespondentID"],
                        "Variable": col,
                        "Rule": rule["rule"],
                        "Value": df.at[idx, col]
                    })

    report_df = pd.DataFrame(issues)

    if not report_df.empty:
        st.write("Validation Report", report_df)

        # Download as Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            report_df.to_excel(writer, index=False, sheet_name="Validation Report")
        st.download_button(
            label="Download Validation Report",
            data=output.getvalue(),
            file_name="validation_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.success("No validation issues found 🎉")
