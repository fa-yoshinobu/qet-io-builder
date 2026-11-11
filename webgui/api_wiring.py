"""Web GUIのwiring処理。"""
from .api_common import (BOUNDARY_DEFAULTS, CONNECTION_DEFAULTS, CONTENT_FIELDS, POSITION_FIELDS, normalize_wiring, _safe)

class WiringApi:
    @_safe
    def wiring(self, index):
        page = self._page(index)
        name = page.get('title') or page.get('tag') or page.get('model') or f'ページ {int(index) + 1}'
        return {'name': name, 'value': normalize_wiring(page.get('wiring')),
                'content_fields': CONTENT_FIELDS, 'position_fields': POSITION_FIELDS,
                'defaults': {'boundaries': BOUNDARY_DEFAULTS, 'connections': CONNECTION_DEFAULTS}}


    @_safe
    def set_wiring(self, index, value):
        page = self._page(index)
        value = normalize_wiring(value)
        previous = page.get('wiring')
        if value['boundaries'] or value['connections'] or value['terminal_plan']:
            page['wiring'] = value
        else:
            page.pop('wiring', None)
        if page.get('wiring') != previous:
            self._touch()
        return {**self.page(index), 'pages': self.snapshot()['pages'], 'dirty': self._dirty}
