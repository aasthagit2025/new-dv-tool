import streamlit as st
import pandas as pd
import pyreadstat
import re

st.set_page_config(page_title="Data Validation Tool", layout="wide")
st.title("🛠 Data Validation Tool")

# File Upload
uploaded_file = st.file_uploader("Upload data file", type=["csv", "xlsx", "sav"])

# Load Data
df = None
if uploaded_file is not None:
    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    elif uploaded_file.name.endswith(".xlsx"):
        df = pd.read_excel(uploaded_file)
    elif uploaded_file.name.endswith(".sav"):
        df, meta = pyreadstat.read_sav(uploaded_file)

    st.success(f"File loaded successfully with {df.shape[0]} rows and {df.shape[1]} columns")
    st.dataframe(df.head())

# Load Validation Rules
rules_file = st.file_uploader("Upload Validation Rules (CSV)", type=["csv"])
rules_df = None
if rules_file is not None:
    rules_df = pd.read_csv(rules_file)
    st.write("### Rules Preview")
    st.dataframe(rules_df.head())

# --- Validation Functions ---
def check_missing(df, variable):
    return df[variable].isna()

def check_range(df, variable, min_val, max_val):
    return ~df[variable].between(min_val, max_val, inclusive="both")

def check_skip(df, variable, condition_var, condition_val):
    return (df[condition_var] == condition_val) & (df[variable].isna())

def check_multiselect(df, prefix):
    multi_vars = [col for col in df.columns if col.startswith(prefix)]
    invalid_values = df[multi_vars].applymap(lambda x: x not in [0,1]).any(axis=1)
    all_zero = (df[multi_vars].sum(axis=1) == 0)
    return invalid_values | all_zero

def check_straightlining(df, grid_prefix):
    grid_vars = [col for col in df.columns if col.startswith(grid_prefix)]
    return df[grid_vars].nunique(axis=1) == 1

def check_openend_junk(series):
    junk_patterns = [
        r"^[a-z]$", r"^[0-9]+$", r"^asdf$", r"^test$", r"(.)\1{3,}"
    ]
    return series.astype(str).apply(
        lambda x: any(re.match(p, x.lower()) for p in junk_patterns)
    )

def check_ai_generated(series):
    ai_like = ["as an ai", "i am unable", "thank you for asking", "in conclusion", "overall,"]
    return series.astype(str).apply(
        lambda x: any(phrase in x.lower() for phrase in ai_like) or len(x.split()) > 50
    )

# --- Run Checks ---
if df is not None and rules_df is not None:
    results = {}

    for _, rule in rules_df.iterrows():
        var = rule["Variable"]
        rule_type = rule["RuleType"]

        if rule_type == "MISSING":
            results[var] = check_missing(df, var)
        elif rule_type == "RANGE":
            results[var] = check_range(df, var, rule["Min"], rule["Max"])
        elif rule_type == "SKIP":
            results[var] = check_skip(df, var, rule["ConditionVar"], rule["ConditionVal"])
        elif rule_type == "MULTISELECT":
            results[var] = check_multiselect(df, rule["Prefix"])
        elif rule_type == "STRAIGHTLINE":
            results[var] = check_straightlining(df, rule["Prefix"])
        elif rule_type == "OE_JUNK":
            results[var] = check_openend_junk(df[var])
        elif rule_type == "OE_AI":
            results[var] = check_ai_generated(df[var])

    # Compile Results
    error_df = pd.DataFrame(results)
    st.write("### Validation Results")
    st.dataframe(error_df)

    # Download option
    csv = error_df.to_csv(index=False).encode("utf-8")
    st.download_button("Download Validation Results", data=csv, file_name="validation_results.csv", mime="text/csv")
