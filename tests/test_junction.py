import unittest
import gen_io_page as gen


class JunctionTest(unittest.TestCase):
    def test_terminal_references_follow_replacement(self):
        symbols=gen.build_symbols()
        self.assertNotEqual(symbols['junction'].terminals['e'][0], symbols['node'].terminals['e'][0])
        page=gen.Page(symbols)
        middle=page.place('junction',100,100)
        a=page.place('node',50,100)
        b=page.place('node',150,100)
        page.wire(a,'e',middle,'w')
        page.wire(middle,'e',b,'w')
        page.finish()
        self.assertTrue(page.elements[0].get('type').endswith('node.elmt'))
        self.assertEqual(page.conductors[0].get('terminal2'),symbols['node'].terminals['w'][0])
        self.assertEqual(page.conductors[1].get('terminal1'),symbols['node'].terminals['e'][0])

    def test_three_wire_junction_keeps_dot(self):
        symbols=gen.build_symbols(); page=gen.Page(symbols)
        middle=page.place('junction',100,100)
        for i,key in enumerate(('w','e','n')):
            endpoint=page.place('node',50+i*50,50)
            page.wire(middle,key,endpoint,'s')
        page.finish()
        self.assertTrue(page.elements[0].get('type').endswith('junction.elmt'))

if __name__=='__main__': unittest.main()
