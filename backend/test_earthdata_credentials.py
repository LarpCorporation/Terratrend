"""Local credential persistence: no real credentials, account or keyring access."""
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import nasa_data


class TestRememberedEarthdata(unittest.TestCase):
    def setUp(self):
        import earthdata_credentials as credentials
        self.c=credentials;self.temp=tempfile.TemporaryDirectory()
        self.paths=patch.object(credentials,'DIRECTORY',Path(self.temp.name)/'terratrend');self.paths.start()
        self.tool=patch.object(credentials,'_find_secret_tool',return_value=None);self.tool.start()
        self.c._cached=None;self.c._backend=None
    def tearDown(self):
        self.paths.stop();self.tool.stop();self.c._cached=None;self.c._backend=None;self.temp.cleanup()

    def test_private_fallback_survives_module_memory_reset_and_has_owner_only_permissions(self):
        self.c.remember('fixture-token-never-a-real-key')
        self.c._cached=None
        self.assertEqual(self.c.load(),'fixture-token-never-a-real-key')
        # Windows exposes no POSIX owner/group/other bits: its per-user
        # application-data directory is protected by ACLs instead.
        if os.name=='posix':
            self.assertEqual(stat.S_IMODE(self.c.DIRECTORY.stat().st_mode),0o700)
            self.assertEqual(stat.S_IMODE((self.c.DIRECTORY/'earthdata-token').stat().st_mode),0o600)
        self.assertTrue(self.c.should_remember())

    def test_desktop_keyring_is_preferred_and_token_is_never_a_process_argument(self):
        def run(args,**kwargs):
            self.assertNotIn('fixture-private-key',args)
            return SimpleNamespace(returncode=0,stdout='fixture-private-key\n' if 'lookup' in args else '')
        with patch.object(self.c,'_find_secret_tool',return_value='/usr/bin/secret-tool'),patch.object(self.c.subprocess,'run',side_effect=run) as run_mock:
            self.c.remember('fixture-private-key');self.c._cached=None
            self.assertEqual(self.c.load(),'fixture-private-key')
        self.assertFalse((self.c.DIRECTORY/'earthdata-token').exists())
        self.assertEqual(run_mock.call_args.kwargs['timeout'],5)

    def test_locked_or_unavailable_keyring_uses_private_fallback(self):
        with patch.object(self.c,'_find_secret_tool',return_value='/usr/bin/secret-tool'),patch.object(self.c.subprocess,'run',side_effect=self.c.subprocess.TimeoutExpired('secret-tool',5)):
            self.c.remember('fixture-private-key');self.c._cached=None
            self.assertEqual(self.c.load(),'fixture-private-key')

    def test_forget_removes_remembered_key_and_preference(self):
        self.c.remember('fixture-private-key');self.c.forget();self.c._cached=None
        self.assertEqual(self.c.load(),'');self.assertFalse(self.c.should_remember())
        self.assertFalse((self.c.DIRECTORY/'earthdata-token').exists())

    def test_forgetting_without_a_prior_opt_in_writes_nothing_to_disk(self):
        # A session-only connection must not create a credential directory: the
        # user never asked to remember anything, and a restricted home
        # directory would make connecting fail outright.
        self.assertFalse(self.c.DIRECTORY.exists())
        self.c.forget()
        self.assertFalse(self.c.DIRECTORY.exists())
        self.assertFalse(self.c.should_remember())

    @unittest.skipUnless(os.name=='posix','Windows has no group/other read bits to weaken')
    def test_loosely_permissioned_credential_file_is_not_read(self):
        self.c.authorize_remember();path=self.c.DIRECTORY/'earthdata-token';path.write_text('fixture-key');path.chmod(0o644)
        self.assertEqual(self.c.load(),'');self.c._cached=None

    def test_symlinked_credential_file_is_not_read(self):
        self.c.authorize_remember();path=self.c.DIRECTORY/'earthdata-token';path.write_text('fixture-key')
        target=Path(self.temp.name)/'other';target.write_text('unrelated')
        try:path.unlink();path.symlink_to(target)
        except (OSError,NotImplementedError) as exc:self.skipTest(f'this platform cannot create symbolic links: {exc}')
        self.c._cached=None
        self.assertEqual(self.c.load(),'')

    def test_status_reports_storage_without_disclosing_a_key(self):
        self.c.remember('fixture-private-key')
        status=self.c.status();self.assertTrue(status['remembered'])
        self.assertNotIn('fixture-private-key',json.dumps(status))

    def test_default_credential_directory_is_outside_the_repository(self):
        repo=Path(__file__).resolve().parent.parent
        default=self.c._default_directory().resolve()
        self.assertNotIn(repo,default.parents)
        if os.name=='nt':
            self.assertIn('TerraTrend',default.parts)

    def test_nasa_token_restores_remembered_connection_after_a_restart(self):
        self.c.remember('fixture-private-key')
        with patch.object(nasa_data,'_TOKEN',''),patch.dict(os.environ,{'EARTHDATA_TOKEN':''}):
            self.assertEqual(nasa_data.token(),'fixture-private-key')

    def test_disconnect_forgets_persisted_connection_and_session(self):
        self.c.remember('fixture-private-key')
        with patch.object(nasa_data,'_TOKEN','fixture-private-key'),patch.dict(os.environ,{'EARTHDATA_TOKEN':''}):
            status=nasa_data.disconnect()
            self.assertFalse(status['configured']);self.assertFalse(status['remembered'])
