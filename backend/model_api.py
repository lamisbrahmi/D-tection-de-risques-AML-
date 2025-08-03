import numpy as np
import pandas as pd
import re
import unidecode
import jellyfish
from flask import Flask, request, jsonify
from flask_cors import CORS
from transformers import pipeline
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from xgboost import XGBClassifier
from sklearn.metrics import accuracy_score, f1_score, classification_report


app = Flask(__name__)
CORS(app)


df = pd.read_excel("AML-stageIA.xlsx")
df.columns = df.columns.str.strip()


translator = pipeline("translation", model="Helsinki-NLP/opus-mt-ar-fr")


def is_arabic(text):
    return any('\u0600' <= c <= '\u06FF' for c in text)


def translate_if_arabic(name):
    if is_arabic(name):
        try:
            return translator(name, max_length=40)[0]['translation_text']
        except:
            return name
    return name


def clean_name(name):
    name = str(name).strip()
    name = re.sub(r'[^\w\s]', '', name)
    name = unidecode.unidecode(name)
    words = name.upper().split()
    words.sort()
    return ' '.join(words)


def translate_and_clean(name):
    return clean_name(translate_if_arabic(name))


df["Cleaned Name"] = df["Full Name"].apply(translate_and_clean)


def levenshtein_distance(s1, s2):
    if len(s1) < len(s2): return levenshtein_distance(s2, s1)
    if len(s2) == 0: return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def soundex_match(a, b):
    return int(a[0] == b[0]) if a and b else 0


def extract_features_ml(input_name, row):
    input_clean = clean_name(input_name)
    db_name = clean_name(row['Cleaned Name'])
    lev_dist = levenshtein_distance(input_clean, db_name)
    lev_score = max(0, 100 - lev_dist * 3)
    sdx_match = soundex_match(jellyfish.soundex(input_clean), jellyfish.soundex(db_name))
    is_high_risk = int(row['Risk Score'] >= 85)
    is_medium_risk = int(70 <= row['Risk Score'] < 85)
    has_nationality_match = int(row['Nationality'] == 'Tunisia')
    return [lev_score, sdx_match, is_high_risk, is_medium_risk, has_nationality_match]


X_ml, y_ml = [], []
for _, row in df.iterrows():
    X_ml.append(extract_features_ml(row['Full Name'], row))
    y_ml.append("Blocked")
    fake_name = ''.join(np.random.choice(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"), max(3, len(row['Full Name']))))
    X_ml.append(extract_features_ml(fake_name, row))
    y_ml.append("Allowed")


X_ml = np.array(X_ml)
le_ml = LabelEncoder()
y_ml_encoded = le_ml.fit_transform(y_ml)


X_train_ml, X_test_ml, y_train_ml, y_test_ml = train_test_split(X_ml, y_ml_encoded, test_size=0.2, stratify=y_ml_encoded)


models_ml = {
    "Random Forest": RandomForestClassifier(n_estimators=100, random_state=42),
    "Logistic Regression": LogisticRegression(max_iter=1000),
    "XGBoost": XGBClassifier(eval_metric="mlogloss")
}


results_ml = {}
for name, model in models_ml.items():
    model.fit(X_train_ml, y_train_ml)
    y_pred = model.predict(X_test_ml)
    results_ml[name] = {
        "model": model,
        "accuracy": accuracy_score(y_test_ml, y_pred),
        "f1": f1_score(y_test_ml, y_pred, average="macro"),
        "report": classification_report(y_test_ml, y_pred, target_names=le_ml.classes_)
    }


@app.route("/predict", methods=["POST"])
def predict():
    data = request.get_json()
    input_name = data.get("name", "")
    if not input_name or input_name.strip() == "" or input_name.strip() == "=":
        return jsonify({"error": "Nom invalide"}), 400

    input_clean = translate_and_clean(input_name)

    
    if input_clean in df["Cleaned Name"].values:
        return jsonify({
            "input_name": input_name,
            "cleaned_name": input_clean,
            "final_decision": "Blocked",
            "reason": "Nom trouvé dans la liste AML"
        })

    df['similarity'] = df['Cleaned Name'].apply(lambda x: levenshtein_distance(input_clean, x))
    best_row = df.loc[df['similarity'].idxmin()]
    df.drop(columns=['similarity'], inplace=True)

    features = np.array(extract_features_ml(input_name, best_row)).reshape(1, -1)

    decisions = []
    for name, data in results_ml.items():
        model = data["model"]
        proba = model.predict_proba(features)[0]
        classes = le_ml.inverse_transform(np.arange(len(proba)))
        decision = classes[np.argmax(proba)]
        decisions.append(decision)

    final_decision = max(set(decisions), key=decisions.count)

    response = {
        "input_name": input_name,
        "cleaned_name": input_clean,
        "models": {}
    }

    for name, data in results_ml.items():
        model = data["model"]
        proba = model.predict_proba(features)[0]
        classes = le_ml.inverse_transform(np.arange(len(proba)))
        decision = classes[np.argmax(proba)]
        response["models"][name] = {
            "decision": decision,
            "probabilities": {cls: round(float(p), 2) for cls, p in zip(classes, proba)},
            "accuracy": round(data["accuracy"], 2),
            "f1_score": round(data["f1"], 2)
        }

    response["final_decision"] = final_decision
    return jsonify(response)

@app.route("/model_stats", methods=["GET"])
def model_stats():
    return jsonify({
        name: {"accuracy": data["accuracy"], "f1_score": data["f1"]}
        for name, data in results_ml.items()
    })
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
