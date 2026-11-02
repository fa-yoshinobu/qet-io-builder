"""機種定義から標準記号または箱型電子機器の端子図の部品を書き出す。"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import gen_io_page as gen
from renderers.standard import export_model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model')
    parser.add_argument('output', type=Path)
    parser.add_argument('--auxiliary', help='機種定義内の補助接点構成ID（1a、1bなど）')
    parser.add_argument('--configuration', help='機種定義内の動作構成ID（light_on等）')
    parser.add_argument('--qet-elements', type=Path)
    args = parser.parse_args()
    models = gen.read_unit_definitions()['standard_device']
    model = args.model.upper()
    if model not in models:
        parser.error('未対応の機種です: ' + model)
    try:
        paths = export_model(model, models[model], args.output, args.auxiliary, args.qet_elements, args.configuration)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print('Exported', len(paths), 'parts to', paths[0].parent)


if __name__ == '__main__':
    main()
