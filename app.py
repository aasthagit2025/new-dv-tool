import pandas as pd
import streamlit as st

st.title("📊 Survey Data Validation Tool")

# Upload survey data
data_file = st.file_uploader("Upload survey data (CSV or SAV)", type=["csv", "sav"])

# Upload validation rules
rules_file = st.file_uploader("Upload validation rules (Excel)", type=["xlsx"])

if data_file and rules_file:
    # Load data
    if data_file.name.endswith(".csv"):
        data = pd.read_csv(data_file)
    else:
        try:
            import pyreadstat
            data, meta = pyreadstat.read_sav(data_file)
        except ImportError:
            st.error("Please install pyreadstat to read SPSS .sav files")
            st.stop()

    st.write("✅ Data loaded successfully", data.shape)

    # Load validation rules
    rules = pd.read_excel(rules_file)

    st.subheader("Validation Results")
    validation_results = []

    for _, rule in rules.iterrows():
        q = rule["question"]

        if q not in data.columns:
            validation_results.append(
                {"question": q, "rule": rule["type"], "status": "⚠️ Question not in dataset"}
            )
            continue

        if rule["type"] == "missing":
            invalid = data[data[q].isna()]
            if not invalid.empty:
                validation_results.append(
                    {"question": q, "rule": "missing", "status": f"{len(invalid)} missing values"}
                )

        elif rule["type"] == "range":
            min_val, max_val = rule["min"], rule["max"]
            invalid = data[(data[q] < min_val) | (data[q] > max_val)]
            if not invalid.empty:
                validation_results.append(
                    {"question": q, "rule": f"range {min_val}-{max_val}", "status": f"{len(invalid)} out of range"}
                )

    if validation_results:
        results_df = pd.DataFrame(validation_results)
        st.dataframe(results_df)
        results_df.to_csv("DV_report.csv", index=False)
        st.download_button("📥 Download Validation Report", results_df.to_csv(index=False), "DV_report.csv")
    else:
        st.success("🎉 No validation issues found!")
