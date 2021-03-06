

import time
import logging
import unittest
from copy import copy

import epics
from ophyd import (PVPositioner, PVPositionerPC, EpicsMotor)
from ophyd import (EpicsSignal, EpicsSignalRO)
from ophyd import (Component as C)

logger = logging.getLogger(__name__)


def setUpModule():
    pass


def tearDownModule():
    logger.debug('Cleaning up')


class PVPosTest(unittest.TestCase):
    sim_pv = 'XF:31IDA-OP{Tbl-Ax:X1}Mtr'

    fake_motor = {'readback': 'XF:31IDA-OP{Tbl-Ax:FakeMtr}-I',
                  'setpoint': 'XF:31IDA-OP{Tbl-Ax:FakeMtr}-SP',
                  'moving': 'XF:31IDA-OP{Tbl-Ax:FakeMtr}Sts:Moving-Sts',
                  'actuate': 'XF:31IDA-OP{Tbl-Ax:FakeMtr}Cmd:Go-Cmd.PROC',
                  'stop': 'XF:31IDA-OP{Tbl-Ax:FakeMtr}Cmd:Stop-Cmd.PROC',
                  }

    def test_pvpos(self):
        motor_record = self.sim_pv
        mrec = EpicsMotor(motor_record, name='pvpos_mrec')
        print('mrec', mrec.describe())
        mrec.wait_for_connection()

        class MyPositioner(PVPositioner):
            '''Setpoint, readback, done, stop. No put completion'''
            setpoint = C(EpicsSignal, '.VAL')
            readback = C(EpicsSignalRO, '.RBV')
            done = C(EpicsSignalRO, '.MOVN')
            stop_signal = C(EpicsSignal, '.STOP')

            @property
            def stop_value(self):
                return 1

            @property
            def done_value(self):
                return 0

        m = MyPositioner(motor_record, name='pos_no_put_compl')
        m.wait_for_connection()

        m.report
        m.read()

        mrec.move(0.1, wait=True)
        time.sleep(0.1)
        self.assertEqual(m.position, 0.1)

        m.stop()
        m.limits

        repr(m)
        str(m)

        mc = copy(m)
        self.assertEqual(mc.describe(), m.describe())

        m.report
        m.read()

    def test_put_complete(self):
        motor_record = self.sim_pv
        # mrec = EpicsMotor(motor_record, name='pcomplete_mrec')
        # print('mrec', mrec.describe())
        # mrec.wait_for_connection()

        logger.info('--> PV Positioner, using put completion and a DONE pv')

        class MyPositioner(PVPositionerPC):
            '''Setpoint, readback, done, stop. Put completion'''
            setpoint = C(EpicsSignal, '.VAL')
            readback = C(EpicsSignalRO, '.RBV')
            done = C(EpicsSignalRO, '.MOVN')

            @property
            def done_value(self):
                return 0

        pos = MyPositioner(motor_record, name='pos_no_put_compl')
        print(pos.describe())
        pos.wait_for_connection()

        pos.report
        pos.read()
        high_lim = pos.setpoint.high_limit
        try:
            pos.check_value(high_lim + 1)
        except ValueError as ex:
            logger.info('Check value for single failed, as expected (%s)', ex)
        else:
            raise ValueError('check_value should have failed')

        stat = pos.move(1, wait=False)
        logger.info('--> post-move request, moving=%s', pos.moving)

        while not stat.done:
            logger.info('--> moving... %s error=%s', stat, stat.error)
            time.sleep(0.1)

        pos.move(-1, wait=True)
        self.assertFalse(pos.moving)

        logger.info('--> PV Positioner, using put completion and no DONE pv')

        class MyPositioner(PVPositionerPC):
            '''Setpoint, readback, put completion. No done pv.'''
            setpoint = C(EpicsSignal, '.VAL')
            readback = C(EpicsSignalRO, '.RBV')

        pos = MyPositioner(motor_record, name='pos_put_compl')
        print(pos.describe())
        pos.wait_for_connection()

        stat = pos.move(2, wait=False)
        logger.info('--> post-move request, moving=%s', pos.moving)

        while not stat.done:
            logger.info('--> moving... %s', stat)
            time.sleep(0.1)

        pos.move(0, wait=True)
        logger.info('--> synchronous move request, moving=%s', pos.moving)

        self.assertFalse(pos.moving)

        pos.report
        pos.read()

    def test_pvpositioner(self):
        def callback(sub_type=None, timestamp=None, value=None, **kwargs):
            logger.info('[callback] [%s] (type=%s) value=%s', timestamp,
                        sub_type, value)

        def done_moving(value=0.0, **kwargs):
            logger.info('Done moving %s', kwargs)

        # ensure we start at 0 for this simple test
        fm = self.fake_motor
        epics.caput(fm['setpoint'], 0.05)
        time.sleep(0.5)
        epics.caput(fm['actuate'], 1)
        time.sleep(0.5)
        epics.caput(fm['setpoint'], 0)
        time.sleep(0.5)
        epics.caput(fm['actuate'], 1)
        time.sleep(0.5)

        class MyPositioner(PVPositioner):
            '''Setpoint, readback, no put completion. No done pv.'''
            setpoint = C(EpicsSignal, fm['setpoint'])
            readback = C(EpicsSignalRO, fm['readback'])
            actuate = C(EpicsSignal, fm['actuate'])
            stop_signal = C(EpicsSignal, fm['stop'])
            done = C(EpicsSignal, fm['moving'])

            @property
            def actuate_value(self):
                return 1

            @property
            def stop_value(self):
                return 1

            @property
            def done_value(self):
                return 1

        pos = MyPositioner('', name='pv_pos_fake_mtr')
        print('fake mtr', pos.describe())
        pos.wait_for_connection()

        pos.subscribe(callback, event_type=pos.SUB_DONE)
        pos.subscribe(callback, event_type=pos.SUB_READBACK)

        logger.info('---- test #1 ----')
        logger.info('--> move to 1')
        pos.move(1, timeout=5)
        self.assertEqual(pos.position, 1)
        logger.info('--> move to 0')
        pos.move(0, timeout=5)
        self.assertEqual(pos.position, 0)

        logger.info('---- test #2 ----')
        logger.info('--> move to 1')
        pos.move(1, wait=False)
        time.sleep(0.5)
        logger.info('--> stop')
        pos.stop()
        logger.info('--> sleep')
        time.sleep(1)
        logger.info('--> move to 0')
        pos.move(0, wait=False, moved_cb=done_moving)
        logger.info('--> post-move request, moving=%s', pos.moving)
        time.sleep(2)

        pos.report
        pos.read()
        repr(pos)
        str(pos)


from . import main
is_main = (__name__ == '__main__')
main(is_main)
