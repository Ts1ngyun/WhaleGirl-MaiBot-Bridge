from pathlib import Path
from unittest.mock import patch
import argparse, importlib.util, json, tempfile, unittest
import install
import restore

class DistributionTests(unittest.TestCase):
    def fixture(self,root):
        whale=root/'whale';mai=root/'mai';instance=root/'instance'
        files={whale/'package.json':'{"version":"4.0.8.1"}',mai/'pyproject.toml':'[project]\nversion="1.4.3"\n',
            instance/'bots/demo/config/bot_config.toml':'[bot]\nnickname="Unchanged"',
            whale/'src/http/routes/index.js':"const modules = [\n  require('./wechat'),\n];",
            instance/'host/model_catalog.toml':'[inner]\nversion="fixture"\n'}
        for p in [mai/'.venv/Scripts/python.exe',mai/'bot.py',whale/'WhaleLauncher.exe',whale/'bridge/engine.py',whale/'bridge/sticker_transport.py']:
            files[p]='fixture only'
        for path,text in files.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')
        return argparse.Namespace(whale_root=str(whale),maibot_root=str(mai),instance_root=str(instance),bot_id='demo',maibot_python=None)

    def test_install_preview_backup_and_no_model_changes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);args=self.fixture(root);release=root/'release';release.mkdir()
            # Copy source-only payload into the fixture; never target a live installation.
            import shutil
            for name in ['whale_patch','plugin']:shutil.copytree(install.ROOT/name,release/name)
            with patch.object(install,'ROOT',release):
                changes=install.plan(args)
                self.assertFalse((release/'data').exists())
                self.assertFalse((Path(args.whale_root)/'data/maibot-link.json').exists())
                with patch('builtins.print'):install.apply(changes)
                self.assertTrue((release/'data/token').is_file())
                self.assertEqual((Path(args.instance_root)/'host/model_catalog.toml').read_text(),'[inner]\nversion="fixture"\n')
                self.assertIn('Unchanged',(Path(args.instance_root)/'bots/demo/config/bot_config.toml').read_text())
                self.assertEqual(len(list((release/'backups').glob('*/restore.json'))),1)
                backup=next((release/'backups').iterdir())
                route=Path(args.whale_root)/'src/http/routes/index.js'
                installed=route.read_bytes()
                route.write_text('changed after install')
                with patch.object(restore,'__file__',str(release/'restore.py')),patch('sys.argv',['restore.py',str(backup),'--apply']),patch('builtins.print'):
                    with self.assertRaises(ValueError):restore.main()
                    self.assertTrue((release/'data/token').exists())
                    route.write_bytes(installed)
                    restore.main()
                self.assertNotIn('maibot-link',route.read_text())
                self.assertFalse((Path(args.whale_root)/'data/maibot-link.json').exists())
                args.bot_id='../other'
                with self.assertRaises(ValueError):install.plan(args)

    def test_version_and_other_installation_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);args=self.fixture(root);whale=Path(args.whale_root)
            (whale/'data').mkdir();(whale/'data/maibot-link.json').write_text(json.dumps({'bridgeRoot':str(root/'another')}))
            with self.assertRaises(ValueError):install.plan(args)
            (whale/'package.json').write_text('{"version":"99.0"}')
            with self.assertRaises(ValueError):install.plan(args)

    def test_no_local_voice_generator_in_distribution(self):
        source=(install.ROOT/'hub.py').read_text(encoding='utf-8')
        self.assertNotIn("web.post('/v1/audio/speech'",source)
        self.assertNotIn("web.post('/adapter/voice'",source)
        bridge=(install.ROOT/'whale_patch/bridge/maibot_async.py').read_text(encoding='utf-8')
        self.assertNotIn('import local_rvc_voice',bridge)
        self.assertFalse((install.ROOT/'local-voice').exists())
