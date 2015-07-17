"""
Test for basic virt-who operations.

Copyright (C) 2014 Radek Novacek <rnovacek@redhat.com>

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""

import sys
import os
from base import TestBase, unittest
import logging

from mock import patch, Mock

from virtwho import parseOptions, VirtWho, OptionError, Queue, Job
from config import Config
from virt import HostGuestAssociationReport, Hypervisor, Guest


class TestOptions(TestBase):
    def setUp(self):
        self.clearEnv()

    def clearEnv(self):
        for key in os.environ.keys():
            if key.startswith("VIRTWHO"):
                del os.environ[key]

    def test_default_cmdline_options(self):
        sys.argv = ["virtwho.py"]
        _, options = parseOptions()
        self.assertFalse(options.debug)
        self.assertFalse(options.background)
        self.assertFalse(options.oneshot)
        self.assertEqual(options.interval, 600)
        self.assertEqual(options.smType, 'sam')
        self.assertEqual(options.virtType, None)

    def test_minimum_interval_options(self):
        sys.argv = ["virtwho.py", "--interval=5"]
        _, options = parseOptions()
        self.assertEqual(options.interval, 600)

    def test_options_debug(self):
        sys.argv = ["virtwho.py", "-d"]
        _, options = parseOptions()
        self.assertTrue(options.debug)

        sys.argv = ["virtwho.py"]
        os.environ["VIRTWHO_DEBUG"] = "1"
        _, options = parseOptions()
        self.assertTrue(options.debug)

    def test_options_virt(self):
        for virt in ['esx', 'hyperv', 'rhevm']:
            self.clearEnv()
            sys.argv = ["virtwho.py", "--%s" % virt, "--%s-owner=owner" % virt,
                        "--%s-env=env" % virt, "--%s-server=localhost" % virt,
                        "--%s-username=username" % virt,
                        "--%s-password=password" % virt]
            _, options = parseOptions()
            self.assertEqual(options.virtType, virt)
            self.assertEqual(options.owner, 'owner')
            self.assertEqual(options.env, 'env')
            self.assertEqual(options.server, 'localhost')
            self.assertEqual(options.username, 'username')
            self.assertEqual(options.password, 'password')

            sys.argv = ["virtwho.py"]
            virt_up = virt.upper()
            os.environ["VIRTWHO_%s" % virt_up] = "1"
            os.environ["VIRTWHO_%s_OWNER" % virt_up] = "xowner"
            os.environ["VIRTWHO_%s_ENV" % virt_up] = "xenv"
            os.environ["VIRTWHO_%s_SERVER" % virt_up] = "xlocalhost"
            os.environ["VIRTWHO_%s_USERNAME" % virt_up] = "xusername"
            os.environ["VIRTWHO_%s_PASSWORD" % virt_up] = "xpassword"
            _, options = parseOptions()
            self.assertEqual(options.virtType, virt)
            self.assertEqual(options.owner, 'xowner')
            self.assertEqual(options.env, 'xenv')
            self.assertEqual(options.server, 'xlocalhost')
            self.assertEqual(options.username, 'xusername')
            self.assertEqual(options.password, 'xpassword')

    def test_options_virt_satellite(self):
        for virt in ['esx', 'hyperv', 'rhevm']:
            self.clearEnv()
            sys.argv = ["virtwho.py",
                        "--satellite",
                        "--satellite-server=localhost",
                        "--satellite-username=username",
                        "--satellite-password=password",
                        "--%s" % virt,
                        "--%s-server=localhost" % virt,
                        "--%s-username=username" % virt,
                        "--%s-password=password" % virt]
            _, options = parseOptions()
            self.assertEqual(options.virtType, virt)
            self.assertEqual(options.owner, '')
            self.assertEqual(options.env, '')
            self.assertEqual(options.server, 'localhost')
            self.assertEqual(options.username, 'username')
            self.assertEqual(options.password, 'password')

            sys.argv = ["virtwho.py"]
            virt_up = virt.upper()
            os.environ["VIRTWHO_SATELLITE"] = "1"
            os.environ["VIRTWHO_SATELLITE_SERVER"] = "xlocalhost"
            os.environ["VIRTWHO_SATELLITE_USERNAME"] = "xusername"
            os.environ["VIRTWHO_SATELLITE_PASSWORD"] = "xpassword"
            os.environ["VIRTWHO_%s" % virt_up] = "1"
            os.environ["VIRTWHO_%s_SERVER" % virt_up] = "xlocalhost"
            os.environ["VIRTWHO_%s_USERNAME" % virt_up] = "xusername"
            os.environ["VIRTWHO_%s_PASSWORD" % virt_up] = "xpassword"
            _, options = parseOptions()
            self.assertEqual(options.virtType, virt)
            self.assertEqual(options.owner, '')
            self.assertEqual(options.env, '')
            self.assertEqual(options.server, 'xlocalhost')
            self.assertEqual(options.username, 'xusername')
            self.assertEqual(options.password, 'xpassword')

    def test_missing_option(self):
        for smType in ['satellite', 'sam']:
            for virt in ['libvirt', 'vdsm', 'esx', 'hyperv', 'rhevm']:
                for missing in ['server', 'username', 'password', 'env', 'owner']:
                    self.clearEnv()
                    sys.argv = ["virtwho.py", "--%s" % virt]
                    if virt in ['libvirt', 'esx', 'hyperv', 'rhevm']:
                        if missing != 'server':
                            sys.argv.append("--%s-server=localhost" % virt)
                        if missing != 'username':
                            sys.argv.append("--%s-username=username" % virt)
                        if missing != 'password':
                            sys.argv.append("--%s-password=password" % virt)
                        if missing != 'env':
                            sys.argv.append("--%s-env=env" % virt)
                        if missing != 'owner':
                            sys.argv.append("--%s-owner=owner" % virt)

                    if virt not in ('libvirt', 'vdsm') and missing != 'password':
                        if smType == 'satellite' and missing in ['env', 'owner']:
                            continue
                        print(smType, virt, missing)
                        self.assertRaises(OptionError, parseOptions)

    @patch('virt.Virt.fromConfig')
    @patch('manager.Manager.fromOptions')
    def test_sending_guests(self, fromOptions, fromConfig):
        options = Mock()
        options.oneshot = True
        options.interval = 0
        options.print_ = False
        fromConfig.return_value.config.name = 'test'
        virtwho = VirtWho(self.logger, options, config_dir="/nonexistant")
        config = Config("test", "esx", "localhost", "username", "password", "owner", "env")
        virtwho.configManager.addConfig(config)
        virtwho.queue = Queue()
        virtwho.queue.put(HostGuestAssociationReport(config, {'a': ['b']}))
        virtwho.run()

        fromConfig.assert_called_with(self.logger, config)
        self.assertTrue(fromConfig.return_value.start.called)
        fromOptions.assert_called_with(self.logger, options)


class TestJobs(TestBase):
    def setupVirtWho(self, oneshot=True):
        options = Mock()
        options.oneshot = oneshot
        options.interval = 0
        options.print_ = False
        virtwho = VirtWho(self.logger, options, config_dir="/nonexistant")
        config = Config("test", "esx", "localhost", "username", "password", "owner", "env")
        virtwho.configManager.addConfig(config)
        return virtwho

    def test_adding_job(self):
        virtwho = self.setupVirtWho()
        # Mock out a method we want to call
        virtwho.send = Mock()
        fake_report = 'fake_report'
        # Add an actual job to be executed immediately
        test_job = Job('send', [fake_report])
        virtwho.addJob(test_job)
        virtwho.run()
        virtwho.send.assert_called_with(fake_report)

    def test_adding_tuple_of_job(self):
        # We should be able to pass in tuples like below and achieve the same
        # result as if we passed in a Job object

        # (target, [args], executeInSeconds, executeAfter)
        fake_report = 'fakereport'
        test_job_tuple = ('send', [fake_report])
        virtwho = self.setupVirtWho()
        virtwho.send = Mock()
        virtwho.addJob(test_job_tuple)
        virtwho.run()
        virtwho.send.assert_called_with(fake_report)


class TestSend(TestBase):
    @patch('manager.Manager.fromOptions')
    def test_send_same_twice(self, fromOptions):
        options = Mock()
        options.interval = 0
        options.oneshot = True
        options._print = False
        virtwho = VirtWho(self.logger, options, config_dir="/nonexistant")

        config = Config('test', 'esx', 'localhost', 'username', 'password', 'owner','env')
        config2 = Config('test2', 'esx', 'localhost', 'username', 'password', 'owner', 'env')
        fake_virt = Mock()
        fake_virt.CONFIG_TYPE = 'esx'
        test_hypervisor = Hypervisor('test', guestIds=[Guest('guest1', fake_virt, 1)])
        assoc = {'hypervisors': [test_hypervisor]}
        fake_report = HostGuestAssociationReport(config, assoc)
        virtwho.configManager.addConfig(config)
        virtwho.configManager.addConfig(config2)

        self.assertTrue(virtwho.send(fake_report))
        # if the report is the same we should not send it
        self.assertFalse(virtwho.send(fake_report))
