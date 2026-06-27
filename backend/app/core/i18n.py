from pathlib import Path
import yaml

translations = {}

for file in Path("app/locales").glob("*.yaml"):
    lang = file.stem
    with open(file, "r", encoding="utf-8") as f:
        translations[lang] = yaml.safe_load(f)


def t(key: str, lang: str = "zh_CN"):
    data = translations.get(lang, {})

    for k in key.split("."):
        data = data.get(k)
        if data is None:
            return key

    return data