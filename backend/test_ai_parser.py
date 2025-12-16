import importlib.util
import pathlib
from pprint import pprint


def load_ai_module():
    root = pathlib.Path.cwd()
    mod_path = root / 'backend' / 'ai.py'
    spec = importlib.util.spec_from_file_location('ai_module', str(mod_path))
    ai = importlib.util.module_from_spec(spec)
    loader = spec.loader
    loader.exec_module(ai)
    return ai


def run_examples(ai):
    examples = [
        'совещание с командой завтра в 11:00',
        'купить цветы маме на др 12 марта',
        'срочно! доделать презентацию к пятнице',
        'паспорт сделать в конце месяца',
        'зубной в четверг запись',
        'абвгд'
    ]

    for ex in examples:
        print('\n=== Пример:', ex)
        res = ai.extract_task_via_gigachat(ex)
        pprint(res)


if __name__ == '__main__':
    ai = load_ai_module()
    run_examples(ai)
