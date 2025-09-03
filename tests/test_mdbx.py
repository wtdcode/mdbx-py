#!/usr/bin/env python3
# Copyright 2021 Noel Kuntze <noel.kuntze@contauro.com> for Contauro AG
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted only as authorized by the OpenLDAP
# Public License.
#
# A copy of this license is available in the file LICENSE in the
# top-level directory of the distribution or, alternatively, at
# <http://www.OpenLDAP.org/license.html>.
#
import ctypes
import inspect

import sys
import subprocess
import random
import unittest
import os
import string
import tempfile
import mdbx
import logging


logging.getLogger("mdbx").setLevel("DEBUG")
MDBX_TEST_DIR = "%s/MDBX_TEST" % tempfile.gettempdir()
MDBX_TEST_DB_NAME = "MDBX_TEST_DB_NAME"
MDBX_TEST_MAP_NAME = "MDBX_TEST_MAP_NAME"
MDBX_TEST_KEY = bytes("MDBX_TEST_KEY", "utf-8")
MDBX_TEST_VAL_BINARY = bytes([0xAA, 0xBB, 0xCC, 0x0])
MDBX_TEST_VAL_UTF8 = bytes("MDBX_TEST_VAL_UTF8", "utf-8")
# Cleanup
subprocess.run(["rm", "-rf", MDBX_TEST_DIR, "default_db"])
subprocess.run(["mkdir", "-p", MDBX_TEST_DIR])


def id_generator(size=6, chars=string.ascii_uppercase + string.digits):
    return "".join(random.choice(chars) for _ in range(size))


class TestMdbx(unittest.TestCase):

    def test_open(self):
        MDBX_TEST_DB_DIR = "%s/%s" % (MDBX_TEST_DIR, inspect.stack()[0][3])
        _db = mdbx.Env(MDBX_TEST_DB_DIR, maxdbs=1)

    def test_write(self):
        MDBX_TEST_DB_DIR = "%s/%s" % (MDBX_TEST_DIR, inspect.stack()[0][3])
        db = mdbx.Env(MDBX_TEST_DB_DIR, maxdbs=1)
        txn = db.start_transaction()
        dbi = txn.open_map()
        dbi.put(txn, MDBX_TEST_KEY, MDBX_TEST_VAL_BINARY)
        txn.commit()
        del txn
        del dbi

        txn = db.start_transaction()

        dbi = txn.open_map()
        self.assertEqual(dbi.get(txn, MDBX_TEST_KEY), MDBX_TEST_VAL_BINARY)
        self.assertEqual(dbi.get_stat(txn).ms_entries, 1)
        db.close()

    def test_db_readitem_writeitem(self):
        MDBX_TEST_DB_DIR = "%s/%s" % (MDBX_TEST_DIR, inspect.stack()[0][3])
        db = mdbx.Env(MDBX_TEST_DB_DIR, maxdbs=1)
        db[MDBX_TEST_KEY] = MDBX_TEST_VAL_UTF8
        self.assertEqual(db[MDBX_TEST_KEY], MDBX_TEST_VAL_UTF8)
        db.close()

    def test_db_iter(self):
        MDBX_TEST_DB_DIR = "%s/%s" % (MDBX_TEST_DIR, inspect.stack()[0][3])
        db = mdbx.Env(MDBX_TEST_DB_DIR, maxdbs=1024)
        db_pairs = {}
        txn = db.start_transaction()
        for i in range(15):
            name = id_generator()
            dbi = txn.create_map(name)
            db_pairs[name] = []

            for i in range(1024):
                pair = (id_generator(), id_generator())
                db_pairs[name].append(pair)
                dbi.put(txn, pair[0].encode("utf-8"), pair[1].encode("utf-8"))
        txn.commit()
        del txn
        dbi.close()
        del dbi
        del db
        # read all keys and compare
        db = mdbx.Env(MDBX_TEST_DB_DIR, maxdbs=1024)
        txn = db.start_transaction(flags=mdbx.MDBXTXNFlags.MDBX_TXN_RDONLY)
        for db_name, pairs in db_pairs.items():
            dbi = txn.open_map(db_name)
            for key, val in pairs:
                self.assertEqual(dbi.get(txn, key.encode("utf-8")).decode("utf-8"), val)
        db.close()

    def test_success_close_written_map(self):
        MDBX_TEST_DB_DIR = "%s/%s" % (MDBX_TEST_DIR, inspect.stack()[0][3])
        db = mdbx.Env(MDBX_TEST_DB_DIR, maxdbs=1024)
        txn = db.start_transaction()
        opened_map = txn.create_map(MDBX_TEST_DB_NAME)
        opened_map.put(txn, MDBX_TEST_KEY, MDBX_TEST_VAL_UTF8)
        txn.commit()
        opened_map.close()
        db.close()

    def test_multi_write(self):
        MDBX_TEST_DB_DIR = "%s/%s" % (MDBX_TEST_DIR, inspect.stack()[0][3])
        geo = mdbx.Geometry(-1, -1, 2147483648, -1, -1, -1)
        db = mdbx.Env(MDBX_TEST_DB_DIR, maxdbs=1024, geometry=geo)
        generated_db_names = {}
        for i in range(16):
            name = id_generator().encode("utf-8")
            if name not in generated_db_names:
                generated_db_names[name] = {}
                ref = generated_db_names[name]
                txn = db.start_transaction()
                dbi = txn.create_map(name)
                for k in range(1024):
                    new_key = id_generator().encode("utf-8")
                    if new_key not in ref:
                        new_val = id_generator().encode("utf-8")
                        ref[new_key] = new_val
                        dbi.put(txn, new_key, new_val)
                txn.commit()
                dbi.close()

        txn.commit()
        db.close()

        db = mdbx.Env(MDBX_TEST_DB_DIR, maxdbs=1024)
        txn = db.start_transaction(mdbx.MDBXTXNFlags.MDBX_TXN_RDONLY)
        for name in generated_db_names:
            ref = generated_db_names[name]
            dbi = txn.open_map(name)
            for old_key, old_val in ref.items():
                self.assertEqual(dbi.get(txn, old_key), old_val)
            dbi.close()
        txn.abort()
        db.close()

    def test_replace(self):
        MDBX_TEST_DB_DIR = "%s/%s" % (MDBX_TEST_DIR, inspect.stack()[0][3])
        db = mdbx.Env(MDBX_TEST_DB_DIR, maxdbs=1024)
        txn = db.start_transaction()
        dbi = txn.open_map()
        dbi.put(txn, MDBX_TEST_KEY, MDBX_TEST_VAL_BINARY)
        txn.commit()

        txn = db.start_transaction()
        dbi = txn.open_map()
        old = dbi.replace(txn, MDBX_TEST_KEY, MDBX_TEST_VAL_UTF8)
        self.assertEqual(old, MDBX_TEST_VAL_BINARY)
        txn.commit()

        txn = db.start_transaction()
        dbi = txn.open_map()
        new = dbi.get(txn, MDBX_TEST_KEY)
        self.assertEqual(new, MDBX_TEST_VAL_UTF8)
        txn.commit()
        db.close()

    def test_delete(self):
        MDBX_TEST_DB_DIR = "%s/%s" % (MDBX_TEST_DIR, inspect.stack()[0][3])
        db = mdbx.Env(MDBX_TEST_DB_DIR, maxdbs=1024)
        txn = db.rw_transaction()
        dbi = txn.create_map("multi", mdbx.MDBXDBFlags.MDBX_DUPSORT)
        dbi.put(txn, MDBX_TEST_KEY, MDBX_TEST_VAL_BINARY)
        dbi.put(txn, MDBX_TEST_KEY, MDBX_TEST_VAL_UTF8)
        txn.commit()

        txn = db.rw_transaction()
        dbi = txn.open_map("multi")
        dbi.delete(txn, MDBX_TEST_KEY, MDBX_TEST_VAL_BINARY)
        utf8 = dbi.get(txn, MDBX_TEST_KEY)
        self.assertEqual(utf8, MDBX_TEST_VAL_UTF8)
        dbi.delete(txn, MDBX_TEST_KEY)
        txn.commit()
        db.close()

    def test_env(self):
        """
        Test all env related methods, except reading and writing
        """

        MDBX_TEST_DB_DIR = "%s/%s" % (MDBX_TEST_DIR, inspect.stack()[0][3])
        env = mdbx.Env(MDBX_TEST_DB_DIR, maxdbs=1)
        env.register_thread()
        txn = env.start_transaction()
        stats = env.get_stat(txn)
        self.assertIsInstance(stats, mdbx.MDBXStat)
        self.assertTrue(str(stats))
        envinfo = env.get_info(txn)
        self.assertIsInstance(envinfo, mdbx.MDBXEnvinfo)
        self.assertTrue(str(envinfo))

        ret_env = txn.get_env()
        self.assertIsInstance(ret_env, mdbx.Env)

        dbi = txn.open_map()
        dbi.put(txn, MDBX_TEST_KEY, MDBX_TEST_VAL_UTF8)
        txn.commit()

        if sys.platform != "win32":
            path = "%s/%s" % (MDBX_TEST_DB_DIR, "copy")
            with open(path, "w") as fd:
                env.copy2fd(
                    fd,
                    mdbx.MDBXCopyMode.MDBX_CP_DEFAULTS
                    | mdbx.MDBXCopyMode.MDBX_CP_FORCE_DYNAMIC_SIZE,
                )

            self.assertTrue(os.path.exists(path))
            self.assertTrue(os.stat(path).st_size > 0)

            txn = env.start_transaction()
            old = dbi.replace(txn, MDBX_TEST_KEY, MDBX_TEST_VAL_BINARY)
            self.assertEqual(old, MDBX_TEST_VAL_UTF8)

            txn.commit()

        env.close()

        env = mdbx.Env(MDBX_TEST_DB_DIR, maxdbs=1)
        txn = env.start_transaction()
        dbi = txn.open_map()
        if sys.platform != "win32":
            self.assertEqual(dbi.get(txn, MDBX_TEST_KEY), MDBX_TEST_VAL_BINARY)
        dbi.drop(txn, MDBX_TEST_KEY)
        self.assertEqual(dbi.get(txn, MDBX_TEST_KEY), None)
        txn.commit()

        txn = env.start_transaction()
        self.assertEqual(dbi.get(txn, MDBX_TEST_KEY), None)
        txn.commit()

        env.get_maxkeysize()
        env.get_maxvalsize()

        env.set_option(mdbx.MDBXOption.MDBX_opt_txn_dp_initial, 2048)
        self.assertEqual(
            env.get_option(mdbx.MDBXOption.MDBX_opt_txn_dp_initial), 2048
        )

        env.get_fd()

        env.sync()

        env.close()

    def test_userctx(self):
        MDBX_TEST_DB_DIR = "%s/%s" % (MDBX_TEST_DIR, inspect.stack()[0][3])
        env = mdbx.Env(MDBX_TEST_DB_DIR, maxdbs=1)

        test_obj = {"foo": "bar"}
        env.set_user_ctx(test_obj)

        self.assertEqual(env.get_user_ctx(), test_obj)

        s = "Foobar".encode("utf-8")

        char_string = ctypes.c_char_p(s)

        env.set_user_ctx_int(char_string)

        self.assertEqual(
            ctypes.cast(env.get_user_ctx_int(), ctypes.c_char_p).value,
            char_string.value,
        )

        txn = env.start_transaction()

        txn.set_user_ctx(test_obj)

        self.assertEqual(txn.get_user_ctx(), test_obj)

        txn.set_user_ctx_int(char_string)

        self.assertEqual(
            ctypes.cast(txn.get_user_ctx_int(), ctypes.c_char_p).value,
            char_string.value,
        )

        txn.abort()

    def test_txn(self):
        MDBX_TEST_DB_DIR = "%s/%s" % (MDBX_TEST_DIR, inspect.stack()[0][3])
        env = mdbx.Env(MDBX_TEST_DB_DIR, maxdbs=1)
        txn = env.start_transaction(mdbx.MDBXTXNFlags.MDBX_TXN_RDONLY)

        txn.reset()

        txn.renew()

    # def test_hsr(self):
    #   import threading
    #   import time
    #   # Need to think this all over first before a situation can be caused when the HSR function would be called
    #   # can not test reasonably for equality of returned function ptr of get_hsr and set_hsr because
    #   # the objects can not be compared for equality and the function pointer is not accessible
    #   # Also, this test currently doesn't do anything useful
    #   return
    #   def hsr_func(env: ctypes.POINTER(mdbx.MDBXEnv), txn: ctypes.POINTER(mdbx.MDBXTXN), pid: ctypes.c_int, tid: ctypes.c_int, laggard: ctypes.c_uint64, gap: ctypes.c_uint, space: ctypes.c_size_t, retry: ctypes.c_int) -> ctypes.c_int:
    #       print("hsr_func called")
    #       shared.append({"pid" : pid, "tid" : tid, "laggard" : laggard, "gap" : gap, "space" : space, "retry" : retry })
    #       with condition:
    #           condition.notify_all()

    #   def stall(**kw_args):
    #       # This function needs to
    #       env=mdbx.Env(kw_args["env_name"], maxdbs=1)
    #       txn=env.start_transaction(mdbx.MDBXTXNFlags.MDBX_TXN_RDONLY)
    #       time.sleep(5)
    #       txn.abort()

    #   MDBX_TEST_DB_DIR="%s/%s" % (MDBX_TEST_DIR, inspect.stack()[0][3])
    #   # Set low space limit and write it until it's full, then start read transaction and a second write transaction,

    #   env=mdbx.Env(MDBX_TEST_DB_DIR, maxdbs=1)
    #   env.set_hsr(mdbx._lib.MDBX_hsr_func(hsr_func))

    #   shared = []
    #   condition=threading.Condition()

    #   thread=threading.Thread(target=stall, kwargs={"env_name" : MDBX_TEST_DIR })
    #   thread.start()
    #   with condition:
    #       condition.wait(timeout=10.0)
    #   self.assertTrue(shared)
    #   thread.join()

    # # def test_rls(self):
    # # Need to think this over too
    # #   def rls_func()

    def test_get_build_info(self):
        mdbx.get_build_info()

    def test_get_version_info(self):
        mdbx.get_version_info()

    def test_get_sysram(self):
        try:
            mdbx._lib.mdbx_get_sysraminfo
        except Exception:
            return True
        a = ctypes.c_int()
        b = ctypes.c_int()
        c = ctypes.c_int()
        self.assertFalse(
            mdbx._lib.mdbx_get_sysraminfo(
                ctypes.byref(a), ctypes.byref(b), ctypes.byref(c)
            )
        )

    def test_txnid(self):
        MDBX_TEST_DB_DIR = "%s/%s" % (MDBX_TEST_DIR, inspect.stack()[0][3])
        env = mdbx.Env(MDBX_TEST_DB_DIR, maxdbs=1)

        txn = env.start_transaction()
        self.assertTrue(txn.id())

    def test_cursor_bind(self):
        return
        # Haven't succeeded in making this work
        # MDBX_TEST_DB_DIR="%s/%s" % (MDBX_TEST_DIR, inspect.stack()[0][3])
        # env=mdbx.Env(MDBX_TEST_DB_DIR, maxdbs=1)

        # txn=env.start_transaction()

        # dbi=txn.open_map()

        # cursor=mdbx.Cursor()
        # cursor.bind(txn, dbi)
        # cursor.put(MDBX_TEST_KEY, MDBX_TEST_VAL_UTF8)
        # self.assertEqual(MDBX_TEST_VAL_UTF8, cursor.get(MDBX_TEST_KEY))
        # self.assertTrue(cursor.eof())
        # self.assertTrue(cursor.on_first())
        # self.assertTrue(cursor.on_last())
        # cursor.delete()

    def test_cursor_open(self):
        MDBX_TEST_DB_DIR = "%s/%s" % (MDBX_TEST_DIR, inspect.stack()[0][3])
        a = "abc".encode("utf-8")
        b = "def".encode("utf-8")
        env = mdbx.Env(MDBX_TEST_DB_DIR, maxdbs=2)

        txn = env.start_transaction()

        dbi = txn.open_map(MDBX_TEST_DB_NAME, flags=mdbx.MDBXDBFlags.MDBX_CREATE)

        cursor = mdbx.Cursor(dbi, txn)

        cursor.put(MDBX_TEST_KEY, MDBX_TEST_VAL_UTF8)
        self.assertEqual(MDBX_TEST_VAL_UTF8, cursor.get(MDBX_TEST_KEY))
        # with self.assertRaises(mdbx.MDBXErrorExc):
        cursor.get(MDBX_TEST_KEY, mdbx.MDBXCursorOp.MDBX_FIRST)

        cursor.get(a)
        cursor.put(a, b)

        txn.commit()
        logging.getLogger("mdbx").debug(
            f"Status, txn={txn._txn}, cursor={cursor._cursor}, dbi={dbi._dbi}"
        )
        txn = env.start_transaction()
        logging.getLogger("mdbx").debug(f"New dbi, dbi = {dbi._dbi}")
        dbi = txn.open_map(MDBX_TEST_DB_NAME)
        logging.getLogger("mdbx").debug(f"New Cursor, dbi = {dbi._dbi}")
        cursor = mdbx.Cursor(dbi, txn)
        self.assertEqual(MDBX_TEST_VAL_UTF8, dbi.get(txn, MDBX_TEST_KEY))
        self.assertEqual(b, cursor.get(a, cursor_op=mdbx.MDBXCursorOp.MDBX_SET))

        cursor.get(MDBX_TEST_KEY, mdbx.MDBXCursorOp.MDBX_NEXT)

        cursor.get(MDBX_TEST_KEY, mdbx.MDBXCursorOp.MDBX_NEXT)
        self.assertTrue(cursor.eof())
        cursor.get(MDBX_TEST_KEY, mdbx.MDBXCursorOp.MDBX_FIRST)
        self.assertTrue(cursor.on_first())
        self.assertFalse(cursor.on_last())
        cursor.get(MDBX_TEST_KEY, mdbx.MDBXCursorOp.MDBX_LAST)
        self.assertTrue(cursor.on_last())
        self.assertFalse(cursor.on_first())
        cursor.delete()


if __name__ == "__main__":
    unittest.main()
