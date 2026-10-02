import json
import re

VALUE = re.compile(r"^[A-Za-z0-9_.,:/=+@ -]*$")
FIELD = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def load(text):
    book = json.loads(text).get("recipes")
    if not isinstance(book, dict) or not book:
        raise ValueError("a recipe file holds a non-empty 'recipes' object")
    for name, recipe in book.items():
        if ("run" in recipe) == ("fanout" in recipe):
            raise ValueError(f"recipe {name} needs exactly one of 'run' and 'fanout'")
        if not isinstance(recipe.get("needs", []), list):
            raise ValueError(f"recipe {name}: 'needs' is a list")
        for metric, pattern in recipe.get("metrics", {}).items():
            if re.compile(pattern).groups < 1:
                raise ValueError(f"recipe {name}: metric {metric} needs a group")
        if "fanout" in recipe:
            fan = recipe["fanout"]
            child = book.get(fan.get("recipe"))
            if child is None or "run" not in child:
                raise ValueError(f"recipe {name}: its fanout names no runnable recipe")
            if "value" not in re.compile(fan["pattern"], re.M).groupindex:
                raise ValueError(f"recipe {name}: its fanout pattern needs a 'value' group")
    return book


def command(recipe, params):
    filled = dict(recipe.get("params", {}))
    for key, value in params.items():
        if key not in filled:
            raise ValueError(f"unknown parameter {key}")
        filled[key] = str(value)
    for key, value in filled.items():
        if not VALUE.match(str(value)):
            raise ValueError(f"parameter {key} holds a character recipes refuse")
    missing = [key for key in FIELD.findall(recipe["run"]) if key not in filled]
    if missing:
        raise ValueError(f"the recipe uses undeclared parameters {missing}")
    return FIELD.sub(lambda match: str(filled[match.group(1)]), recipe["run"])


def fanout(recipe, text):
    fan = recipe["fanout"]
    pattern = re.compile(fan["pattern"], re.M)
    return [
        {"recipe": fan["recipe"], "params": {fan["param"]: match.group("value").strip()}, "needs": list(fan.get("needs", []))}
        for match in pattern.finditer(text)
    ]


def metrics(recipe, output):
    found = {}
    for name, pattern in recipe.get("metrics", {}).items():
        matches = re.findall(pattern, output)
        if not matches:
            continue
        value = matches[-1][0] if isinstance(matches[-1], tuple) else matches[-1]
        try:
            found[name] = float(value)
        except ValueError:
            found[name] = value
    return found
