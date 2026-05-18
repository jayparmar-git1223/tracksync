"""
test_suite.py — Full Test Suite v2
"""
import sys, os, tempfile, gzip, shutil
SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, SRC)
import unittest

RTF = r"""{\rtf1\ansi\deff0
1   Kick In
2   Snare Top
3   OH L
4   OH R
5   Lead Vox
6   BGV 1
7   GTR L
8   GTR R
9   Bass DI
10  Keys L
11  Keys R
}"""

def make_session(n=4):
    from models.session import Session
    from models.track import Track, GROUP_DRUMS, GROUP_VOCALS, GROUP_GUITARS
    g=[GROUP_DRUMS,GROUP_VOCALS,GROUP_GUITARS,GROUP_DRUMS]
    n2=["Kick In","Lead Vox","GTR L","Snare Top"]
    return Session(console="DiGiCo",session_name="Test Show",sample_rate=48000,bit_depth=24,
                   tracks=[Track(channel=i+1,name=n2[i%4],group=g[i%4]) for i in range(n)])

class TestModels(unittest.TestCase):
    def test_track_roundtrip(self):
        from models.track import Track, GROUP_DRUMS
        t=Track(channel=3,name="OH L",group=GROUP_DRUMS,stereo_pair=4)
        t2=Track.from_dict(t.to_dict())
        self.assertEqual(t.channel,t2.channel); self.assertEqual(t.stereo_pair,t2.stereo_pair)
    def test_session_json_roundtrip(self):
        s=make_session(4)
        with tempfile.NamedTemporaryFile(suffix=".json",delete=False) as f: p=f.name
        try:
            s.save_json(p); s2=s.__class__.load_json(p)
            self.assertEqual(s.get_track_count(),s2.get_track_count())
        finally: os.unlink(p)
    def test_session_groups(self):
        s=make_session(4); self.assertIn("DRUMS",s.get_unique_groups())
    def test_bus_roundtrip(self):
        from models.bus import Bus
        b=Bus(name="Drum Bus",channels=[1,2,3]); b2=Bus.from_dict(b.to_dict())
        self.assertEqual(b.name,b2.name)

class TestDigiCoParser(unittest.TestCase):
    def _parse(self,content):
        from parser.digico_parser import DiGiCoParser
        with tempfile.NamedTemporaryFile(suffix=".rtf",mode="w",delete=False,encoding="utf-8") as f:
            f.write(content); p=f.name
        try: return DiGiCoParser().parse(p)
        finally: os.unlink(p)
    def test_track_count(self): self.assertGreater(self._parse(RTF).get_track_count(),0)
    def test_kick_classified(self):
        s=self._parse(RTF); kick=next(t for t in s.tracks if "Kick" in t.name)
        self.assertEqual(kick.group,"DRUMS")
    def test_vox_classified(self):
        s=self._parse(RTF); vox=next(t for t in s.tracks if "Vox" in t.name)
        self.assertEqual(vox.group,"VOCALS")
    def test_stereo_pairs(self):
        s=self._parse(RTF)
        oh_l=next((t for t in s.tracks if t.name=="OH L"),None)
        oh_r=next((t for t in s.tracks if t.name=="OH R"),None)
        if oh_l and oh_r: self.assertEqual(oh_l.stereo_pair,oh_r.channel)
    def test_real_file(self):
        p=os.path.join(os.path.dirname(__file__),"sample_digico_report.rtf")
        if not os.path.exists(p): self.skipTest("sample file missing")
        from parser.digico_parser import DiGiCoParser
        s=DiGiCoParser().parse(p); self.assertEqual(s.get_track_count(),30)

class TestYamahaParser(unittest.TestCase):
    CSV="""CH,Name,Patch\n1,Kick In,L1\n2,Snare Top,L2\n3,OH L,L3\n4,OH R,L4\n5,Lead Vox,L5\n"""
    def _parse(self,c,ext=".csv"):
        from parser.yamaha_parser import YamahaParser
        with tempfile.NamedTemporaryFile(suffix=ext,mode="w",delete=False,encoding="utf-8") as f:
            f.write(c); p=f.name
        try: return YamahaParser().parse(p)
        finally: os.unlink(p)
    def test_csv_tracks(self): self.assertGreater(self._parse(self.CSV).get_track_count(),0)
    def test_console_name(self): self.assertIn("Yamaha",self._parse(self.CSV).console)
    def test_xml_format(self):
        xml="""<?xml version="1.0"?><YamahaProAudioData><InputChannel CH="1"><Name>Kick</Name></InputChannel><InputChannel CH="2"><Name>Snare</Name></InputChannel></YamahaProAudioData>"""
        s=self._parse(xml,".cel"); self.assertGreater(s.get_track_count(),0)

class TestAllenHeathParser(unittest.TestCase):
    SCENE="""<?xml version="1.0"?><Scene><Input Number="1"><Name>Kick In</Name></Input><Input Number="2"><Name>Snare</Name></Input><Input Number="3"><Name>Lead Vox</Name></Input></Scene>"""
    def _parse(self,c):
        from parser.allen_heath_parser import AllenHeathParser
        with tempfile.NamedTemporaryFile(suffix=".scene",mode="w",delete=False,encoding="utf-8") as f:
            f.write(c); p=f.name
        try: return AllenHeathParser().parse(p)
        finally: os.unlink(p)
    def test_tracks(self): self.assertGreater(self._parse(self.SCENE).get_track_count(),0)
    def test_console(self): self.assertIn("Allen",self._parse(self.SCENE).console)

class TestAvidParser(unittest.TestCase):
    CSV="""Input#,Name,Source\n1,Kick In,L1\n2,Snare Top,L2\n3,Lead Vox,L3\n4,GTR,L4\n"""
    def _parse(self,c):
        from parser.avid_parser import AvidS6LParser
        with tempfile.NamedTemporaryFile(suffix=".csv",mode="w",delete=False,encoding="utf-8") as f:
            f.write(c); p=f.name
        try: return AvidS6LParser().parse(p)
        finally: os.unlink(p)
    def test_tracks(self): self.assertGreater(self._parse(self.CSV).get_track_count(),0)
    def test_console(self): self.assertIn("Avid",self._parse(self.CSV).console)

class TestREAPERExporter(unittest.TestCase):
    def test_creates_rpp(self):
        from exporters.reaper.reaper_exporter import REAPERExporter
        s=make_session(4)
        with tempfile.TemporaryDirectory() as d:
            out=REAPERExporter().export(s,os.path.join(d,"show.rpp"))
            self.assertTrue(out.endswith(".rpp"))
            c=open(out).read()
            self.assertIn("<REAPER_PROJECT",c); self.assertIn("Kick In",c)
    def test_empty_raises(self):
        from exporters.reaper.reaper_exporter import REAPERExporter
        from exporters.base_exporter import ExporterError
        from models.session import Session
        with self.assertRaises(ExporterError): REAPERExporter().export(Session(),"/tmp/x.rpp")

class TestCubaseExporter(unittest.TestCase):
    def test_creates_xml(self):
        from exporters.cubase.cubase_exporter import CubaseExporter
        s=make_session(4)
        with tempfile.TemporaryDirectory() as d:
            out=CubaseExporter().export(s,os.path.join(d,"show"))
            c=open(out).read()
            self.assertIn("tracklist",c); self.assertIn("Kick In",c)

class TestProToolsExporter(unittest.TestCase):
    def test_session_txt(self):
        from exporters.protools.protools_exporter import ProToolsExporter
        s=make_session(4)
        with tempfile.TemporaryDirectory() as d:
            out=ProToolsExporter().export(s,os.path.join(d,"show"))
            c=open(out).read()
            self.assertIn("SESSION NAME:",c); self.assertIn("Kick In",c)

class TestAbletonExporter(unittest.TestCase):
    def test_valid_gzip_als(self):
        from exporters.ableton.ableton_exporter import AbletonExporter
        s=make_session(4)
        with tempfile.TemporaryDirectory() as d:
            out=AbletonExporter().export(s,os.path.join(d,"show.als"))
            with gzip.open(out,"rb") as f: c=f.read().decode("utf-8")
            self.assertIn("Ableton",c); self.assertIn("Kick In",c)

class TestLogicExporter(unittest.TestCase):
    def test_creates_files(self):
        from exporters.logic.logic_exporter import LogicExporter
        s=make_session(4)
        with tempfile.TemporaryDirectory() as d:
            LogicExporter().export(s,os.path.join(d,"show"))
            self.assertTrue(os.path.exists(os.path.join(d,"show_logic_scripter.js")))
            self.assertTrue(os.path.exists(os.path.join(d,"show_logic_tracks.xml")))

class TestRegistry(unittest.TestCase):
    def setUp(self):
        import registry; registry._PARSERS=[]; registry._EXPORTERS=[]; registry._initialized=False
    def test_parsers_registered(self):
        from registry import list_parsers; self.assertGreater(len(list_parsers()),0)
    def test_exporters_registered(self):
        from registry import list_exporters; self.assertGreater(len(list_exporters()),0)
    def test_get_parser_rtf(self):
        from registry import get_parser; p=get_parser(".rtf"); self.assertIn("DiGiCo",p.console_name)
    def test_get_parser_cel(self):
        from registry import get_parser; p=get_parser(".cel"); self.assertIn("Yamaha",p.console_name)
    def test_get_exporter_reaper(self):
        from registry import get_exporter; e=get_exporter("REAPER"); self.assertEqual(e.daw_name,"REAPER")
    def test_get_exporter_alias_pt(self):
        from registry import get_exporter; e=get_exporter("pt"); self.assertIn("Pro Tools",e.daw_name)
    def test_get_exporter_ableton(self):
        from registry import get_exporter; self.assertIsNotNone(get_exporter("ableton"))
    def test_get_exporter_logic(self):
        from registry import get_exporter; self.assertIsNotNone(get_exporter("logic"))
    def test_unknown_returns_none(self):
        from registry import get_exporter; self.assertIsNone(get_exporter("DAW9000"))

class TestPresets(unittest.TestCase):
    def setUp(self): self.d=tempfile.mkdtemp()
    def tearDown(self): shutil.rmtree(self.d,ignore_errors=True)
    def _pm(self):
        from routing_presets import PresetManager; return PresetManager(templates_dir=self.d)
    def test_builtin_presets(self):
        pm=self._pm(); names=[p.name for p in pm.list_presets()]
        self.assertIn("Live Show",names)
    def test_apply_creates_buses(self):
        pm=self._pm(); s=make_session(4); s=pm.apply_preset(s,"live_show")
        self.assertGreater(len(s.buses),0)
    def test_click_overridden_to_misc(self):
        from models.session import Session; from models.track import Track
        pm=self._pm()
        s=Session(tracks=[Track(channel=1,name="Click",group="DRUMS"),Track(channel=2,name="Kick In",group="DRUMS")])
        s=pm.apply_preset(s,"live_show")
        click=next(t for t in s.tracks if t.name=="Click"); self.assertEqual(click.group,"MISC")
    def test_save_load_custom(self):
        from routing_presets import RoutingPreset,PresetManager
        pm=self._pm(); c=RoutingPreset(name="My Preset",description="test")
        pm.save_preset(c,"my_preset"); loaded=pm.load_preset("my_preset")
        self.assertEqual(loaded.name,"My Preset")

class TestSessionDiff(unittest.TestCase):
    def test_identical_no_changes(self):
        from session_diff import SessionDiff; s=make_session(4)
        self.assertFalse(SessionDiff(s,s).has_changes())
    def test_detects_added(self):
        from session_diff import SessionDiff,CHANGE_ADDED; from models.track import Track
        s1=make_session(3); s2=make_session(3); s2.tracks.append(Track(channel=99,name="New"))
        diff=SessionDiff(s1,s2); changes=diff.compare()
        self.assertIn(CHANGE_ADDED,[c.change_type for c in changes if hasattr(c,"change_type")])
    def test_detects_rename(self):
        from session_diff import SessionDiff,CHANGE_RENAMED
        s1=make_session(2); s2=make_session(2); s2.tracks[0].name="Completely Different"
        diff=SessionDiff(s1,s2); changes=diff.compare()
        self.assertIn(CHANGE_RENAMED,[c.change_type for c in changes if hasattr(c,"change_type")])
    def test_report_str(self):
        from session_diff import SessionDiff; s=make_session(2)
        self.assertIn("SESSION COMPARISON",SessionDiff(s,s).report())
    def test_to_dict(self):
        from session_diff import SessionDiff; s=make_session(2)
        d=SessionDiff(s,s).to_dict(); self.assertIn("total_changes",d)

class TestSettings(unittest.TestCase):
    def setUp(self): self.d=tempfile.mkdtemp()
    def tearDown(self): shutil.rmtree(self.d,ignore_errors=True)
    def _s(self):
        from settings import Settings; return Settings(config_dir=self.d)
    def test_default_daw(self): self.assertEqual(self._s().get("default_daw"),"REAPER")
    def test_set_persists(self):
        s=self._s(); s.set("default_daw","Cubase"); s2=self._s()
        self.assertEqual(s2.get("default_daw"),"Cubase")
    def test_attribute_access(self): self.assertEqual(self._s().theme,"dark")
    def test_reset(self):
        s=self._s(); s.set("default_daw","Logic Pro"); s.reset_to_defaults()
        self.assertEqual(s.get("default_daw"),"REAPER")

class TestClassification(unittest.TestCase):
    def _c(self,n):
        from parser.digico_parser import classify_track; return classify_track(n)
    def test_kick(self): self.assertEqual(self._c("Kick In"),"DRUMS")
    def test_snare(self): self.assertEqual(self._c("Snare Top"),"DRUMS")
    def test_overhead(self): self.assertEqual(self._c("OH L"),"DRUMS")
    def test_vocal(self): self.assertEqual(self._c("Lead Vox"),"VOCALS")
    def test_bgv(self): self.assertEqual(self._c("BGV 1"),"VOCALS")
    def test_guitar(self): self.assertEqual(self._c("GTR L"),"GUITARS")
    def test_bass(self): self.assertEqual(self._c("Bass DI"),"BASS")
    def test_piano(self): self.assertEqual(self._c("Piano L"),"KEYS")
    def test_misc(self): self.assertEqual(self._c("Zylophone9000"),"MISC")

if __name__=="__main__":
    print("="*60+"\n  Live Console → DAW Mirror — Full Test Suite\n"+"="*60+"\n")
    r=unittest.TextTestRunner(verbosity=2).run(
        unittest.TestLoader().loadTestsFromModule(sys.modules[__name__]))
    print(f"\n{'✓ ALL '+str(r.testsRun)+' TESTS PASSED' if r.wasSuccessful() else '✗ FAILURES: '+str(len(r.failures))}")
    sys.exit(0 if r.wasSuccessful() else 1)
