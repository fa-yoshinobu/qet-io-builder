"""JSON/QET またはメーカーの全機種を native QET CLI で A3 PDF に出力する。

python tools/qet_export_pdf.py project.json [output.pdf] [--qet-exe PATH]
python tools/qet_export_pdf.py --manufacturer keyence --output-dir PDF
python tools/qet_export_pdf.py --list-manufacturers
"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import os
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from tools.pdf_to_a3 import to_a3


def find_qet(explicit=None):
    requested = explicit or os.environ.get('QET_EXE')
    if requested:
        found = shutil.which(str(requested))
        if found:
            return found
        raise FileNotFoundError(f'指定したQETが見つかりません: {requested}')
    found = shutil.which('qelectrotech') or shutil.which('qelectrotech.exe')
    if found:
        return found
    for directory in (os.environ.get('ProgramFiles'), os.environ.get('ProgramFiles(x86)'),
                      '/Applications/qelectrotech.app/Contents/MacOS'):
        if not directory:
            continue
        candidate = Path(directory) / ('qelectrotech' if directory.endswith('MacOS') else 'QElectroTech/bin/qelectrotech.exe')
        if candidate.is_file():
            return str(candidate)
    raise FileNotFoundError('QETが見つかりません。--qet-exe または環境変数 QET_EXE を指定してください。')


def export(qet_path, pdf_path, qet_exe=None, timeout=600):
    """PDFを検証・A3化した後だけ置換する。既存のQET画面/設定を触らない。"""
    source, destination = Path(qet_path).resolve(), Path(pdf_path).resolve()
    if destination.suffix.lower() != '.pdf':
        raise ValueError('出力先は .pdf を指定してください')
    expected = len(ET.parse(source).getroot().findall('diagram'))
    if not expected:
        raise ValueError('図面ページがありません')
    executable = find_qet(qet_exe)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix='qet_pdf_') as folder:
        folder = Path(folder)
        temporary = folder / 'native.pdf'
        settings = folder / 'settings'
        settings.mkdir()
        env = dict(os.environ, QET_SETTINGS_DIR=str(settings))
        result = subprocess.run([executable, '--export-pdf', str(source), str(temporary)],
                                env=env, capture_output=True, text=True, errors='replace', timeout=timeout)
        if result.returncode:
            raise RuntimeError('QETのPDF出力に失敗しました。--export-pdf対応版が必要です。\n'
                               + result.stdout + result.stderr)
        with temporary.open('rb') as handle:
            actual = len(PdfReader(handle).pages)
        if actual != expected:
            raise ValueError(f'PDFページ数が一致しません: QET {expected}, PDF {actual}')
        to_a3(str(temporary), native=True)
        with temporary.open('rb') as handle:
            if len(PdfReader(handle).pages) != expected:
                raise ValueError('A3変換後のページ数が一致しません')
        os.replace(temporary, destination)
    return expected


def export_input(source, destination, qet_exe=None, timeout=600):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source.suffix.lower() == '.qet':
        return export(source, destination, qet_exe, timeout)
    if source.suffix.lower() != '.json':
        raise ValueError('入力は .json または .qet を指定してください')
    import gen_io_page
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix='qet_build_') as folder:
        qet = Path(folder) / destination.with_suffix('.qet').name
        gen_io_page.main(str(source), str(qet))
        pages = export(qet, destination, qet_exe, timeout)
        # 作成したQETも再編集できるようPDFと同じ場所へ残す。
        os.replace(qet, destination.with_suffix('.qet'))
    return pages


def export_catalog(manufacturer, output_dir, qet_exe=None, timeout=600):
    from tools.catalog_qet import manufacturers, build_category
    catalog = manufacturers()
    chosen = sorted(catalog) if manufacturer == 'all' else [manufacturer]
    if any(maker not in catalog for maker in chosen):
        raise ValueError('未登録のメーカーです。--list-manufacturers で確認してください')
    executable = find_qet(qet_exe)
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for maker in chosen:
        with tempfile.TemporaryDirectory(dir=output_dir, prefix='qet_catalog_') as folder:
            folder = Path(folder)
            writer = PdfWriter()
            expected = 0
            try:
                for category, models in catalog[maker].items():
                    qet = build_category(category, models, folder / category)
                    pdf = qet.with_suffix('.pdf')
                    pages = export(qet, pdf, executable, timeout)
                    expected += pages
                    writer.append(str(pdf))
                    print(f'{maker}/{category}: {len(models)}機種 / {pages}ページ', flush=True)
                merged = folder / (maker + '.pdf')
                with merged.open('wb') as handle:
                    writer.write(handle)
            finally:
                writer.close()
            with merged.open('rb') as handle:
                if len(PdfReader(handle).pages) != expected:
                    raise ValueError('結合後のPDFページ数が一致しません')
            destination = output_dir / merged.name
            os.replace(merged, destination)
            results.append((destination, expected))
            print(f'完了: {destination} ({expected}ページ)', flush=True)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('source', nargs='?')
    parser.add_argument('output', nargs='?')
    parser.add_argument('--qet-exe')
    parser.add_argument('--timeout', type=float, default=600, help='QET処理1回の上限秒数（既定600）')
    parser.add_argument('--manufacturer', help='メーカー名、または all')
    parser.add_argument('--output-dir', default='PDF')
    parser.add_argument('--list-manufacturers', action='store_true')
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error('--timeout は正の秒数を指定してください')
    try:
        if args.list_manufacturers:
            from tools.catalog_qet import manufacturers
            for maker, categories in manufacturers().items():
                print(maker, sum(len(models) for models in categories.values()))
        elif args.manufacturer:
            if args.source or args.output:
                parser.error('--manufacturer と入力ファイルは同時指定できません')
            export_catalog(args.manufacturer, args.output_dir, args.qet_exe, args.timeout)
        elif args.source:
            output = args.output or str(Path(args.source).with_suffix('.pdf'))
            pages = export_input(args.source, output, args.qet_exe, args.timeout)
            print(f'完了: {Path(output).resolve()} ({pages}ページ)')
        else:
            parser.error('入力ファイルまたは --manufacturer を指定してください')
    except (OSError, ValueError, RuntimeError, PdfReadError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f'PDF出力エラー: {error}\n')


if __name__ == '__main__':
    main()
