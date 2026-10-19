import importlib
import os
import sys
import types
import unittest


PLUGIN_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, "plugin")
)
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

fake_rlpy = types.SimpleNamespace(
    RStatus=types.SimpleNamespace(Success="success"),
)
sys.modules["RLPy"] = fake_rlpy
render = importlib.import_module("iclone_mcp_tool_render")


class Time:
    def __init__(self, value):
        self.value = value


class Fps:
    def GetFrameIndex(self, time_value):
        return time_value.value // 10

    def IndexedFrameTime(self, frame):
        return Time(frame * 10)


class RenderGlobal:
    output_size = types.SimpleNamespace(
        nWidth=1920, nHeight=1080, bUsingViewportResolution=False
    )
    settings = types.SimpleNamespace(
        nActiveRenderMode=1,
        kPreview=types.SimpleNamespace(
            nRenderMode=0,
            nBounceCount=4,
            nReferenceDiffuseBounceCount=2,
            nEffectiveBounceCount=2,
            strBouncePrecedence="reference_diffuse",
            nAccumulationTarget=16,
            nStartSample=3,
            nRealtimeSamplesPerPixel=8,
            bReferenceDenoiser=False,
            bRealtimeDenoiser=True,
            bMotionBlur=False,
        ),
        kFinal=types.SimpleNamespace(
            nRenderMode=1,
            nBounceCount=8,
            nReferenceDiffuseBounceCount=8,
            nEffectiveBounceCount=8,
            strBouncePrecedence="equal",
            nAccumulationTarget=64,
            nStartSample=3,
            nRealtimeSamplesPerPixel=0,
            bReferenceDenoiser=True,
            bRealtimeDenoiser=False,
            bMotionBlur=True,
        ),
    )
    progress = types.SimpleNamespace(
        nCurrentSample=12,
        nTargetSample=64,
        fConvergence=0.1875,
        fProgress=0.5,
        nElapsedMilliseconds=250,
        nCurrentFrame=5,
        nStartFrame=0,
        nEndFrame=10,
        nRenderMode=1,
        bActive=True,
    )
    statistics = types.SimpleNamespace(
        nSamples=12,
        nElapsedMilliseconds=250,
        nWidth=1920,
        nHeight=1080,
        bDenoiser=True,
        nGpuMemoryMb=1024,
        nFrameCount=11,
        bCompleted=False,
    )
    calls = []
    job = None
    ignore_size_write = False

    @classmethod
    def GetRenderOutputSize(cls):
        return cls.output_size

    @classmethod
    def SetRenderOutputSize(cls, width, height):
        cls.calls.append(("set_size", width, height))
        if not cls.ignore_size_write:
            cls.output_size.nWidth = width
            cls.output_size.nHeight = height
        return "success"

    @staticmethod
    def GetRenderFrameRange(render_type):
        return types.SimpleNamespace(nStartFrame=2, nEndFrame=8, nFrameCount=7)

    @classmethod
    def GetRenderSettings(cls):
        return cls.settings

    @staticmethod
    def GetRenderSystem():
        return 1

    @staticmethod
    def GetStartTime():
        return Time(0)

    @staticmethod
    def GetEndTime():
        return Time(100)

    @staticmethod
    def GetFps():
        return Fps()

    @staticmethod
    def GetRenderProgress():
        return RenderGlobal.progress

    @staticmethod
    def GetRenderStatistics():
        return RenderGlobal.statistics

    @classmethod
    def StartRender(cls, render_type, start_time, end_time, output_path):
        cls.calls.append(("start", render_type, start_time.value, end_time.value, output_path))
        cls.job = types.SimpleNamespace(
            strJobId="render-1",
            strType="video" if render_type == 1 else "image_sequence",
            strState="queued",
            strPhase="queued",
            strOutputPath=output_path,
            strError="",
            kOutputSize=cls.output_size,
            kFrameRange=types.SimpleNamespace(nStartFrame=0, nEndFrame=10, nFrameCount=11),
            kRequestedSettings=cls.settings,
            kEffectiveSettings=cls.settings,
            kProgress=cls.progress,
            kStatistics=cls.statistics,
            bCancellable=True,
            bCompletion=False,
        )
        return cls.job

    @classmethod
    def GetRenderJob(cls, job_id):
        assert job_id == "render-1"
        return cls.job

    @classmethod
    def CancelRender(cls, job_id):
        assert job_id == "render-1"
        cls.job.strState = "cancelled"
        cls.job.strPhase = "cancelled"
        cls.job.bCancellable = False
        return cls.job


class RenderScene:
    samples = {0: 16, 1: 64}
    ignore_sample_write = False

    @staticmethod
    def GetPathtracerDebugView():
        return 0

    @classmethod
    def GetViewportSamples(cls, mode):
        return cls.samples[mode]

    @classmethod
    def SetViewportSamples(cls, mode, value):
        if not cls.ignore_sample_write:
            cls.samples[mode] = value
        return "success"


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.previous_rlpy = render.RLPy
        render.RLPy = types.SimpleNamespace(
            RStatus=types.SimpleNamespace(Success="success"),
            RGlobal=RenderGlobal,
            RScene=RenderScene,
            VIDEO=1,
            IMAGE_SEQUENCE=2,
        )
        RenderGlobal.calls = []
        RenderGlobal.job = None
        RenderGlobal.output_size.nWidth = 1920
        RenderGlobal.output_size.nHeight = 1080
        RenderGlobal.ignore_size_write = False
        RenderScene.samples = {0: 16, 1: 64}
        RenderScene.ignore_sample_write = False

    def tearDown(self):
        render.RLPy = self.previous_rlpy

    def test_native_settings_size_range_progress_and_statistics(self):
        self.assertEqual(
            render.get_render_output_size({}),
            {
                "width": 1920,
                "height": 1080,
                "using_viewport_resolution": False,
            },
        )
        self.assertEqual(render.set_render_output_size({"width": 1280, "height": 720})["effective"]["width"], 1280)
        self.assertEqual(
            render.get_render_frame_range({"render_type": "video"})["frame_range"]["frame_count"],
            7,
        )
        self.assertEqual(render.get_render_progress({})["target_sample"], 64)
        self.assertEqual(render.get_render_statistics({})["gpu_memory_mb"], 1024)
        settings = render.get_render_settings({})
        self.assertEqual(settings["final"]["bounce_count"], 8)
        self.assertEqual(settings["final"]["bounce_precedence"], "equal")
        self.assertEqual(settings["final"]["start_sample"], 3)
        self.assertEqual(settings["final"]["start_sample_scope"], "preview_and_final")
        self.assertTrue(settings["motion_blur"])

    def test_preview_and_final_sample_counters_are_separate(self):
        self.assertEqual(render.get_viewport_samples({})["preview"], 16)
        self.assertEqual(render.get_viewport_samples({})["final"], 64)
        result = render.set_viewport_samples(
            {"render_mode": "final", "sample_count": 96}
        )
        self.assertEqual(result["effective"], 96)
        self.assertEqual(render.get_viewport_samples({})["preview"], 16)

        unchanged = render.set_viewport_samples(
            {"render_mode": "final", "sample_count": 96}
        )
        self.assertFalse(unchanged["changed"])

        unchanged_size = render.set_render_output_size(
            {"width": 1920, "height": 1080}
        )
        self.assertFalse(unchanged_size["changed"])

    def test_setters_require_observable_readback(self):
        RenderGlobal.ignore_size_write = True
        with self.assertRaises(RuntimeError):
            render.set_render_output_size({"width": 1280, "height": 720})

        RenderScene.ignore_sample_write = True
        with self.assertRaises(RuntimeError):
            render.set_viewport_samples({"render_mode": "final", "sample_count": 96})
        self.assertEqual(render.get_viewport_samples({})["final"], 64)

    def test_render_job_starts_asynchronously_and_cancels_natively(self):
        with self.assertRaises(ValueError):
            render.start_render({"render_type": "video", "frame_start": 0, "frame_end": 0})

        job = render.start_render(
            {
                "render_type": "video",
                "frame_start": 0,
                "frame_end": 10,
            }
        )
        self.assertEqual(job["state"], "queued")
        self.assertEqual(job["requested_render_type"], "video")
        self.assertEqual(RenderGlobal.calls[0], ("start", 1, 0, 100, ""))
        self.assertEqual(render.get_render_job({"job_id": "render-1"})["state"], "queued")
        self.assertEqual(render.cancel_render({"job_id": "render-1"})["state"], "cancelled")


class FakeVisualSettings:
    def __init__(self):
        self.enabled = False
        self.sync_image = False
        self.sync_orientation = False
        self.loaded = None

    def IsIBLEnable(self):
        return self.enabled

    def IsIBLSyncSkyImage(self):
        return self.sync_image

    def IsIBLSyncSkyOrientation(self):
        return self.sync_orientation

    def LoadIBLImage(self, path):
        self.loaded = path
        return "success"

    def SetIBLSyncSkyImage(self, value):
        self.sync_image = value
        return "success"

    def SetIBLSyncSkyOrientation(self, value):
        self.sync_orientation = value
        return "success"

    def SetIBLEnable(self, value):
        self.enabled = value
        return "success"


def test_set_ibl_updates_public_state(tmp_path):
    component = FakeVisualSettings()
    previous = render.RLPy
    fake_rlpy.RGlobal = types.SimpleNamespace(GetVisualSettingComponent=lambda: component)
    fake_rlpy.RStatus = types.SimpleNamespace(Success="success")
    render.RLPy = fake_rlpy
    image = tmp_path / "studio.hdr"
    image.write_bytes(b"hdr")
    try:
        result = render.set_ibl({
            "image_path": str(image),
            "enabled": True,
            "sync_sky_image": True,
            "sync_sky_orientation": True,
        })

        assert result["ibl_enabled"] is True
        assert result["sync_sky_image"] is True
        assert result["sync_sky_orientation"] is True
        assert result["loaded_image_path"] == str(image)
    finally:
        render.RLPy = previous


class _FakeScene:
    def __init__(self):
        self.index = 0
        self.set_indices = []

    def GetPathtracerDebugView(self):
        return self.index

    def SetPathtracerDebugView(self, index):
        self.index = index
        self.set_indices.append(index)
        return "success"


class _FakeGlobal:
    @staticmethod
    def RenderImage(path):
        with open(path, "wb") as output:
            output.write(b"png")
        return "success"


def test_render_multi_pass_writes_outputs_and_restores_view(tmp_path):
    fake_scene = _FakeScene()
    previous = render.RLPy
    fake_rlpy.RScene = fake_scene
    fake_rlpy.RGlobal = _FakeGlobal
    fake_rlpy.RStatus = types.SimpleNamespace(Success="success")
    render.RLPy = fake_rlpy
    try:
        result = render.render_multi_pass({
            "confirm": "RENDER_MULTI_PASS_WITH_CURRENT_SETTINGS",
            "output_dir": str(tmp_path),
            "passes": [
                {"name": "Beauty", "debug_view": "Disabled", "file_name": "beauty.png"},
                {"name": "Diffuse", "debug_view": "FirstHitDiffuse", "file_name": "diffuse.png"},
            ],
        })

        assert [item["name"] for item in result["passes"]] == ["Beauty", "Diffuse"]
        assert (tmp_path / "beauty.png").read_bytes() == b"png"
        assert (tmp_path / "diffuse.png").read_bytes() == b"png"
        assert result["restored_debug_view"] == 0
        assert fake_scene.set_indices == [0, 2, 0]
    finally:
        render.RLPy = previous


if __name__ == "__main__":
    unittest.main()
