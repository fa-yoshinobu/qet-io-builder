"""選んだ制御部品をQETのユーザーコレクションへ登録する。"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import os
from xml.etree import ElementTree as ET


def user_collection_dir():
    if os.name != 'nt':
        raise ValueError('自動登録はWindows用です。「書き出す…」で保存先を指定してください。')
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\QElectroTech\QElectroTech\elements-collections') as key:
            value, _ = winreg.QueryValueEx(key, 'custom-collection-path')
        if value and value != 'default' and Path(value).is_dir():
            return Path(value)
    except OSError:
        pass
    roaming = os.environ.get('APPDATA')
    if not roaming:
        raise ValueError('QETのユーザーコレクションを特定できません。「書き出す…」で保存先を指定してください。')
    modern = Path(roaming) / 'QElectroTech' / 'QElectroTech' / 'elements'
    legacy = Path(roaming) / 'qet' / 'elements'
    return legacy if legacy.is_dir() and not modern.is_dir() else modern


def _category(folder, label):
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / 'qet_directory'
    if not target.exists():
        root = ET.Element('qet-directory')
        names = ET.SubElement(root, 'names')
        for language in ('ja', 'en'):
            ET.SubElement(names, 'name', lang=language).text = label
        ET.indent(root, space='  ')
        ET.ElementTree(root).write(target, encoding='utf-8', xml_declaration=True)


def _identities():
    import gui_core as core
    return {model: (maker, series) for maker, groups in core.part_catalog('standard_model', '').items()
            for series, models in groups.items() for model in models}


def _register(model, identity, root, auxiliary, configuration, definitions=None):
    import gui_core as core
    if identity is None:
        raise ValueError('登録に対応していない部品です: ' + model)
    maker, series = identity
    folder = root / maker / series
    paths = core.export_part(model, folder, auxiliary, configuration, definitions=definitions)
    for directory, label in ((root, 'qet-io-builder'), (root / maker, core.MAKER_NAMES.get(maker, maker)),
                             (folder, core.SERIES_NAMES.get(series, series))):
        _category(directory, label)
    for directory in {path.parent for path in paths}:
        while directory != folder:
            _category(directory, directory.name)
            directory = directory.parent
    return paths


def register_part(model, auxiliary=None, configuration=None):
    model = model.upper()
    identity = _identities().get(model)
    return _register(model, identity, user_collection_dir() / 'qet-io-builder', auxiliary, configuration)


def register_all_parts(models=None):
    import gen_io_page as gen
    identities = _identities()
    selected = sorted(identities) if models is None else list(dict.fromkeys(m.upper() for m in models))
    unknown = set(selected) - identities.keys()
    if unknown:
        raise ValueError('登録に対応していない部品です: ' + ', '.join(sorted(unknown)))
    definitions = gen.read_unit_definitions()
    root = user_collection_dir() / 'qet-io-builder'
    success, paths, errors, configurations = set(), [], [], 0
    for model in selected:
        spec = definitions['standard_device'].get(model, definitions['power_supply'].get(model, {}))
        auxiliaries = [o['id'] for o in spec.get('auxiliary_options', [])] or [None]
        variants = [o['id'] for o in spec.get('configuration_options', [])] or [None]
        for auxiliary in auxiliaries:
            for configuration in variants:
                try:
                    paths += _register(model, identities[model], root, auxiliary, configuration, definitions)
                    success.add(model)
                    configurations += 1
                except (OSError, ValueError) as exc:
                    errors.append(dict(model=model, auxiliary=auxiliary, configuration=configuration, message=str(exc)))
    message = f'{len(success)}機種・{configurations}構成・{len(paths)}部品をQETに登録しました。'
    if errors:
        message += f'\n登録できなかった構成：{len(errors)}件\n' + '\n'.join(e['model'] + ': ' + e['message'] for e in errors[:10])
        if len(errors) > 10:
            message += f'\nほか{len(errors) - 10}件'
    message += '\nQETのユーザーコレクションを更新するか、QETを再起動してください。'
    return dict(ok=not errors, models=len(success), configurations=configurations, parts=len(paths),
                errors=errors, message=message)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__, epilog='登録はGUIの部品書出しメニューから行います。このモジュールは登録APIを提供します。')
    parser.parse_args()
    parser.print_help()
