import json
import random

CATEGORIES = {
    "Health_Medical": ["病院", "風邪", "薬", "健康診断", "ワクチン", "歯医者", "手術"],
    "IT_Tech": ["プログラミング", "Python", "エラー", "パソコン", "スマホ", "AI", "サーバー"],
    "Travel_Leisure": ["旅行", "温泉", "ホテル", "観光", "飛行機", "新幹線", "パスポート"],
    "Food_Cooking": ["ラーメン", "カフェ", "レシピ", "夕飯", "美味しい", "ランチ", "自炊"],
    "Work_Career": ["残業", "会議", "上司", "転職", "面接", "給料", "有給", "プレゼン"],
    "Daily_Life": ["掃除", "洗濯", "眠い", "疲れた", "散歩", "買い物", "天気"]
}

def generate_seed_data(output_path="seed_data.json", samples_per_category=50):
    seed_docs = []
    templates = ["最近、{kw}が気になります。", "{kw}について調べました。", "昨日は{kw}に行きました。"]
    for category, keywords in CATEGORIES.items():
        for _ in range(samples_per_category):
            kw = random.choice(keywords)
            template = random.choice(templates)
            seed_docs.append(template.format(kw=kw))

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(seed_docs, f, ensure_ascii=False, indent=2)
    print(f"Generated {len(seed_docs)} seeds.")

if __name__ == "__main__":
    generate_seed_data()
