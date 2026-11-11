"""機種別JSONからメーカー別の全機種カタログQETを組み立てる。"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import copy
import json
from collections import defaultdict
from xml.etree import ElementTree as ET

import gen_io_page as g
from tools.make_control_sample import Imported
from renderers import standard
from tools.export_power_supply_elements import definition as power_definition

ROOT = Path(__file__).resolve().parents[1]


def manufacturers():
    """partsのメーカー階層を使い、機種一覧を別管理しない。"""
    result = defaultdict(lambda: defaultdict(dict))
    definitions = g.read_unit_definitions()
    for path in sorted((ROOT / 'parts').rglob('*.json')):
        item = json.loads(path.read_text(encoding='utf-8-sig'))
        category, model = item['category'], item['model'].upper()
        maker = path.relative_to(ROOT / 'parts').parts[1]
        result[maker][category][model] = definitions[category][model]
    return result

mapping={'fx5_analog':'fx5analog','iqr_analog':'iqranalog','q_analog':'qanalog','remote_analog':'remoteanalog',
         'got_body':'gotbody','got_option':'gotoption','q_comm':'qcomm','iqr_comm':'iqrcomm','fx5_comm':'fxcomm',
         'q_mixed':'qmixed','iqr_mixed':'iqrmixed','remote_mixed':'remotemixed',
         'remote_pulse':'remotepulse','remote_iolink':'remoteiolink','mx_io':'mxio','inverter':'inverter',
         'kv_io':'kv_io','unit_diagram':'unit_diagram'}
def entry(category,model,spec,definitions):
    if category in mapping:
        kind=mapping[category]
        page=dict(kind=kind,model=model)
        if kind in ('qcomm','iqrcomm','fxcomm','gotoption'):
            page=dict(kind=kind,left_model=model)
        if kind.endswith('analog'):return [(page,[])]
        if kind in ('qmixed','iqrmixed','remotemixed'):
            rows={direction:g.blank_io_rows(uc) for direction,(uc,_) in zip(('in','out'),g.iqr_units(page,{'in':[],'out':[]}))}
            return [(page,rows)]
        return [(page,None)]
    if category in ('iqr_q','remote_io'):
        pg=dict(kind='input' if spec['io']=='in' else 'output',model=model)
        result=[(pg,g.blank_io_rows(pg))]
        if category=='remote_io':result.insert(0,(dict(kind='remotebody',model=model),None))
        return result
    if category in ('fx5_cpu','fx5_ext'):
        kind='fx5u' if category=='fx5_cpu' else 'fx5ext'
        pg=dict(kind=kind,model=model);fs=g.fx_spec(pg)
        def rows(addrs):return [dict(アドレス=a,信号名='',機器番号='',接点='',負荷='',線番='',備考='') for a in addrs]
        result=[(pg,{'in':rows(fs['inputs']),'out':rows([a for _,group in fs['groups'] for a in group])})]
        if category=='fx5_cpu':result.insert(0,(dict(kind='fx5body',model=model),None))
        return result
    if category=='fx5_board':
        return [(dict(kind='fx5body',model='FX5S-30MR/ES' if model=='FX5-SDCD' else 'FX5U-32MR/ES',board_model=model),None)]
    if category=='mx_cpu':
        return [(dict(kind='mxbody',model=model),None),(dict(kind='mxio',model=model),None)]
    if category in ('iqr_cpu','q_cpu','iqr_power','q_power','iqr_base','q_base'):
        q=category.startswith('q_')
        pg=dict(kind='qbody' if q else 'iqrbody',model='Q03UDVCPU' if q else 'R04CPU',
                power_model='Q61P' if q else 'R61P',base_model='Q35B' if q else 'R35B',modules=[])
        if category.endswith('cpu'):pg['model']=model
        elif category.endswith('power'):pg['power_model']=model
        elif spec.get('extension'):
            ext=dict(base_model=model,modules=[])
            if spec.get('power_required',True):ext['power_model']=pg['power_model']
            pg['extensions']=[ext]
        else:pg['base_model']=model
        return [(pg,None)]
    if category=='terminal_block':
        result=[]
        for n,choice in enumerate(spec['compatible']):
            for m,plc in enumerate(choice['models']):
                tag=f'{list(definitions[category]).index(model)+1}_{n+1}_{m+1}'
                result.extend(g.terminal_block_project_pages(model,plc,choice['cable'],'PLC'+tag,'XT'+tag,'W'+tag,
                               tag2='XTB'+tag,cable_tag2='WB'+tag))
        return result
    raise ValueError(category)

def build_category(category, models, out):
    """端子図は既定構成、標準部品は既定の補助接点/構成で全分割部品を載せる。"""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    definitions = g.read_unit_definitions()
    cfg = dict(front_pages=False, project_title='全機種カタログ')
    if category in ('standard_device','power_supply'):
        symbols={k:v for k,v in g.build_symbols().items() if k in ('junction','node')}
        project,_=g.build_project(cfg,[])
        pages=[]
        for model,spec in models.items():
            if category=='power_supply':
                data=[('unit',power_definition(model,spec))]
            else:
                configuration=spec.get('default_configuration') or next((o['id'] for o in spec.get('configuration_options',[])),None)
                auxiliary=spec.get('default_auxiliary_option')
                if spec.get('auxiliary_selection_required') and not auxiliary:
                    auxiliary=spec['auxiliary_options'][0]['id']
                paths=standard.export_model(model,spec,out/'elements',auxiliary,configuration=configuration)
                data=[(path.stem,ET.parse(path).getroot()) for path in paths]
            for part,definition in data:
                name='part'+str(len(symbols))
                roles={str(i):[float(t.get('x')),float(t.get('y'))] for i,t in enumerate(definition.findall('./description/terminal'))}
                symbol=Imported(name,definition,roles);symbols[name]=symbol
                page=g.Page(symbols)
                x=400; y=max(80, 30-min((float(t.get("y", "0")) for t in definition.findall("./description/dynamic_text")), default=0))
                page.place(name,x,y,label='UNIT1')
                element=page.elements[-1]
                infos=element.find('elementInformations')
                for info in definition.findall('./elementInformations/elementInformation'):
                    if info.get('name')!='label':
                        existing=infos.find("elementInformation[@name='%s']"%info.get('name'))
                        if existing is not None:infos.remove(existing)
                        infos.append(copy.deepcopy(info))
                for text in definition.findall('./description/dynamic_text'):
                    text=copy.deepcopy(text);text.tag='dynamic_elmt_text'
                    element.find('dynamic_texts').append(text)
                page.finish();pages.append((model+' '+part,page))
        coll=project.find('./collection/category/category');coll.clear();coll.set('name','plc_io')
        names=ET.SubElement(coll,'names');ET.SubElement(names,'name',lang='ja').text='部品'
        for symbol in symbols.values():coll.append(symbol.to_xml())
        for no,(title,page) in enumerate(pages,1):g.add_diagram(project,g.project_config(cfg),title,no,page)
    else:
        entries=[]
        for model,spec in models.items():
            entries+=entry(category,model,spec,definitions)
        project,_=g.build_project(cfg,entries)
    destination = out / (category + '.qet')
    ET.ElementTree(project).write(destination, encoding='utf-8', xml_declaration=True)
    return destination


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__, epilog='カタログ生成には python tools/qet_export_pdf.py --manufacturer を使用してください。')
    parser.parse_args()
    parser.print_help()
