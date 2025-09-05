import unittest
import tempfile
import shutil
from pathlib import Path
from mdbx import *
import struct

class MDBXIterTest(unittest.TestCase):
    
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self._folder_path = Path(self._folder.name)
        return super().setUp()
    
    def test_iters(self):
        expected = []
        for i in range(10):
            if i == 1:
                continue
            expected.append((struct.pack(">I", i), struct.pack(">I", 10 - i)))
        with Env(self._folder_path.absolute()) as env:
            with env.rw_transaction() as txn:
                with txn.open_map() as dbi:
                    for k, v in expected:
                        dbi.put(txn, k, v)
                    txn.commit()
            
            with env.ro_transaction() as txn:
                with txn.cursor() as cur:
                    k, v = cur.first()
                    self.assertEqual((k, v), expected[0])
                    k, v = cur.last()
                    self.assertEqual((k, v), expected[-1])
                
                with txn.cursor() as cur:
                    vals = [(k,v) for k, v in cur.iter()]
                    self.assertEqual(vals, expected)

                with txn.cursor() as cur:
                    vals = [(k, v) for k, v in cur.iter(start_key=struct.pack(">I", 4))]
                    self.assertEqual(vals, expected[3:])
                    
    def test_iters_dup(self):
        expected = []
        for i in range(10):
            if i == 1:
                continue
            dups = [struct.pack(">I", x) for x in range(5)]
            expected.append((struct.pack(">I", i), tuple(dups)))

        with Env(self._folder_path.absolute(), maxdbs=2) as env:
            with env.rw_transaction() as txn:
                with txn.create_map("test", MDBXDBFlags.MDBX_DUPSORT) as dbi:
                    for k, dups in expected:
                        for d in dups:
                            dbi.put(txn, k, d)
                    txn.commit()
            
            with env.ro_transaction() as txn:
                with txn.cursor("test") as cur:
                    k, v = cur.first()
                    self.assertEqual((k, v), (expected[0][0], expected[0][1][0]))
                    v = cur.first_dup()
                    self.assertEqual(v, expected[0][1][0])
                    v = cur.last_dup()
                    self.assertEqual(v, expected[0][1][-1])
                    k, v = cur.last()
                    self.assertEqual((k, v), (expected[-1][0], expected[-1][1][-1]))
                    v = cur.first_dup()
                    self.assertEqual(v, expected[-1][1][0])
                    v = cur.last_dup()
                    self.assertEqual(v, expected[-1][1][-1])
                
                with txn.cursor("test") as cur:
                    vals = []
                    for row in cur.iter_dupsort_rows():
                        row_vals = {}
                        for k, v in row:
                            if k not in row_vals:
                                row_vals[k] = []
                            row_vals[k].append(v)
                        self.assertEqual(len(row_vals), 1)
                        vals.append((
                            list(row_vals.keys())[0],
                            tuple(list(row_vals.values())[0])
                        ))
                    self.assertEqual(vals, expected)

                with txn.cursor("test") as cur:
                    vals = [(k, v) for k, v in cur.iter_dupsort()]
                    expected = [ (x, dup) for x, dups in expected for dup in dups]
                    self.assertEqual(vals, expected)

    def test_sequence(self) -> None:
        with Env(self._folder_path.absolute().as_posix()) as env:
            with env.ro_transaction() as txn:
                with txn.open_map() as dbi:
                    self.assertEqual(dbi.get_sequence(txn, 0), 0)

            with env.rw_transaction() as txn:
                with txn.open_map() as dbi:
                    self.assertEqual(dbi.get_sequence(txn, 1), 0)
                    self.assertEqual(dbi.get_sequence(txn, 1), 1)
                txn.abort()

            with env.ro_transaction() as txn:
                with txn.open_map() as dbi:
                    self.assertEqual(dbi.get_sequence(txn, 0), 0)

            with env.rw_transaction() as txn:
                with txn.open_map() as dbi:
                    self.assertEqual(dbi.get_sequence(txn, 1), 0)
                    self.assertEqual(dbi.get_sequence(txn, 1), 1)
                txn.commit()

            with env.ro_transaction() as txn:
                with txn.open_map() as dbi:
                    self.assertEqual(dbi.get_sequence(txn, 0), 2)

    def tearDown(self):
        del self._folder
        shutil.rmtree(self._folder_path, ignore_errors=True)
        return super().tearDown()

if __name__ == '__main__':
    unittest.main()
