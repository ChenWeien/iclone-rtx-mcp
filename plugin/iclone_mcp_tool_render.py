import os
import time

import RLPy


_PATH_TRACER_DEBUG_VIEWS = (
    "Disabled",
    "FirstHitBaseColor",
    "FirstHitDiffuse",
    "FirstHitRoughness",
    "FirstHitMetallic",
    "FirstHitFaceNormal",
    "FirstHitGeometryNormal",
    "FirstHitShadingNormal",
    "FirstHitCoatNormal",
    "FirstHitMeanFreePathDistance",
    "FirstHitScatteringColor",
    "FirstHitHairAbsorptionCoef",
    "FirstHitHairLocalTangent",
    "FirstHitHairDiffuseReflectionTint",
    "FirstHitHairMelanin",
    "FirstHitHairMelaninRedness",
    "FirstHitHairRadialRoughness",
    "FirstHitOpacity",
    "FirstHitAlphaThreshold",
    "FirstHitSpecular",
    "FirstHitShadingTangent",
    "FirstHitShadingBitangent",
    "FirstHitIrisNormal",
    "FirstHitEyeCausticNormal",
    "FirstHitIrisMask",
    "FirstHitBarycentrics",
    "FirstHitFrontFacing",
    "FirstHitThinSurface",
    "FirstHitShaderPermutation",
    "rtxcr_Albedo",
    "rtxcr_ssAlbedo",
    "bssrdfWeight",
    "ImagePlaneRayLength",
    "DominantStablePlaneIndex",
    "StablePlaneVirtualRayLength",
    "StablePlaneMotionVectors",
    "StablePlaneNormals",
    "StablePlaneRoughness",
    "StablePlaneDiffBSDFEstimate",
    "StablePlaneDiffRadiance",
    "StablePlaneDiffHitDist",
    "StablePlaneSpecBSDFEstimate",
    "StablePlaneSpecRadiance",
    "StablePlaneSpecHitDist",
    "StablePlaneRelaxedDisocclusion",
    "StablePlaneDiffRadianceDenoised",
    "StablePlaneSpecRadianceDenoised",
    "StablePlaneCombinedRadianceDenoised",
    "StablePlaneViewZ",
    "StablePlaneDenoiserValidation",
    "StableRadiance",
    "VBufferMotionVectors",
    "VBufferDepth",
    "FirstHitOpacityMicroMapInWorld",
    "FirstHitOpacityMicroMapOverlay",
    "SecondarySurfacePosition",
    "SecondarySurfaceRadiance",
    "ReSTIRGIOutput",
    "ReSTIRDIInitialOutput",
    "ReSTIRDITemporalOutput",
    "ReSTIRDISpatialOutput",
    "ReSTIRDIFinalOutput",
    "ReSTIRDIFinalContribution",
    "ReGIRIndirectOutput",
    "OnlyCoat",
    "OnlySheen",
    "OnlyEmissive",
    "OnlyTransmission",
    "OnlySSS",
    "Specular",
)
_PATH_TRACER_DEBUG_VIEW_INDEX = {
    name: index for index, name in enumerate(_PATH_TRACER_DEBUG_VIEWS)
}
_OPTIONAL_DEBUG_VIEWS = (
    {
        "name": "RTXShadowPass",
        "supported": False,
        "reason": "The current public RTX debug-view enum has no RTX Shadow Pass entry.",
    },
)
_TRANSITION_JOBS = {}
_TRANSITION_SEQUENCE = 0


def _enum_value(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _render_system_name(value):
    value = _enum_value(value)
    if value == _enum_value(getattr(RLPy, "ERenderSystem_DX11", 0)):
        return "dx11"
    if value == _enum_value(getattr(RLPy, "ERenderSystem_DX12", 1)):
        return "dx12"
    return "unknown"


def _dto_member(value, name, default=None):
    if value is None:
        return default
    member = getattr(value, name, default)
    return member() if callable(member) else member


def _render_output_size_snapshot(value=None):
    if value is None:
        getter = getattr(RLPy.RGlobal, "GetRenderOutputSize", None)
        if callable(getter):
            value = getter()
        else:
            legacy = RLPy.RGlobal.GetScreenSize(0, 0)
            if not isinstance(legacy, (tuple, list)) or len(legacy) < 3:
                raise RuntimeError("Unexpected response from iClone render settings")
            if legacy[0] != RLPy.RStatus.Success:
                raise RuntimeError("iClone could not read the render size")
            return {
                "width": int(legacy[1]),
                "height": int(legacy[2]),
                "using_viewport_resolution": False,
            }
    if isinstance(value, dict):
        width = value.get("width", value.get("nWidth", 0))
        height = value.get("height", value.get("nHeight", 0))
        viewport = value.get(
            "using_viewport_resolution",
            value.get("bUsingViewportResolution", False),
        )
    else:
        width = _dto_member(value, "nWidth", 0)
        height = _dto_member(value, "nHeight", 0)
        viewport = _dto_member(value, "bUsingViewportResolution", False)
    return {
        "width": int(width),
        "height": int(height),
        "using_viewport_resolution": bool(viewport),
    }


def _pathtracer_settings_snapshot(value):
    if value is None:
        return None
    if isinstance(value, dict):
        get = value.get
    else:
        get = lambda name, default=None: _dto_member(value, name, default)
    return {
        "render_mode": int(get("nRenderMode", get("render_mode", 0))),
        "bounce_count": int(get("nBounceCount", get("bounce_count", 0))),
        "reference_diffuse_bounce_count": int(
            get(
                "nReferenceDiffuseBounceCount",
                get("reference_diffuse_bounce_count", 0),
            )
        ),
        "effective_bounce_count": int(
            get("nEffectiveBounceCount", get("effective_bounce_count", 0))
        ),
        "bounce_precedence": str(
            get("strBouncePrecedence", get("bounce_precedence", ""))
        ),
        "accumulation_target": int(
            get("nAccumulationTarget", get("accumulation_target", 0))
        ),
        "start_sample": int(get("nStartSample", get("start_sample", 0))),
        "start_sample_scope": "preview_and_final",
        "realtime_samples_per_pixel": int(
            get("nRealtimeSamplesPerPixel", get("realtime_samples_per_pixel", 0))
        ),
        "reference_denoiser": bool(
            get("bReferenceDenoiser", get("reference_denoiser", False))
        ),
        "realtime_denoiser": bool(
            get("bRealtimeDenoiser", get("realtime_denoiser", False))
        ),
        "motion_blur": bool(get("bMotionBlur", get("motion_blur", False))),
    }


def _render_settings_dto_snapshot(value):
    if value is None:
        return None
    if isinstance(value, dict):
        active_mode = value.get("active_render_mode", value.get("nActiveRenderMode", 0))
        preview = value.get("preview", value.get("kPreview"))
        final = value.get("final", value.get("kFinal"))
    else:
        active_mode = _dto_member(value, "nActiveRenderMode", 0)
        preview = _dto_member(value, "kPreview")
        final = _dto_member(value, "kFinal")
    preview = _pathtracer_settings_snapshot(preview) or {}
    final = _pathtracer_settings_snapshot(final) or {}
    active = final if int(active_mode) == 1 else preview
    return {
        "active_render_mode": int(active_mode),
        "preview": preview,
        "final": final,
        "motion_blur": bool(active.get("motion_blur", False)),
        "start_sample_scope": "preview_and_final",
    }


def _frame_range_snapshot(value):
    if isinstance(value, dict):
        start = value.get("start_frame", value.get("nStartFrame", 0))
        end = value.get("end_frame", value.get("nEndFrame", 0))
        count = value.get("frame_count", value.get("nFrameCount", 0))
    else:
        start = _dto_member(value, "nStartFrame", 0)
        end = _dto_member(value, "nEndFrame", 0)
        count = _dto_member(value, "nFrameCount", 0)
    return {
        "start_frame": int(start),
        "end_frame": int(end),
        "frame_count": int(count),
    }


def _progress_snapshot(value):
    if isinstance(value, dict):
        get = value.get
    else:
        get = lambda name, default=None: _dto_member(value, name, default)
    return {
        "current_sample": int(get("nCurrentSample", get("current_sample", 0))),
        "target_sample": int(get("nTargetSample", get("target_sample", 0))),
        "convergence": float(get("fConvergence", get("convergence", 0.0))),
        "progress": float(get("fProgress", get("progress", 0.0))),
        "elapsed_ms": int(
            get("nElapsedMilliseconds", get("elapsed_ms", 0))
        ),
        "current_frame": int(get("nCurrentFrame", get("current_frame", 0))),
        "start_frame": int(get("nStartFrame", get("start_frame", 0))),
        "end_frame": int(get("nEndFrame", get("end_frame", 0))),
        "render_mode": int(get("nRenderMode", get("render_mode", 0))),
        "active": bool(get("bActive", get("active", False))),
    }


def _statistics_snapshot(value):
    if isinstance(value, dict):
        get = value.get
    else:
        get = lambda name, default=None: _dto_member(value, name, default)
    return {
        "samples": int(get("nSamples", get("samples", 0))),
        "elapsed_ms": int(get("nElapsedMilliseconds", get("elapsed_ms", 0))),
        "width": int(get("nWidth", get("width", 0))),
        "height": int(get("nHeight", get("height", 0))),
        "denoiser": bool(get("bDenoiser", get("denoiser", False))),
        "gpu_memory_mb": int(get("nGpuMemoryMb", get("gpu_memory_mb", 0))),
        "frame_count": int(get("nFrameCount", get("frame_count", 0))),
        "completed": bool(get("bCompleted", get("completed", False))),
    }


def _render_job_snapshot(value):
    if value is None:
        raise RuntimeError("iClone returned no render job")
    if isinstance(value, dict):
        get = value.get
    else:
        get = lambda name, default=None: _dto_member(value, name, default)
    state = str(get("strState", get("state", "")))
    error = str(get("strError", get("error", "")) or "")
    output_size = get("kOutputSize") or get("output_size")
    frame_range = get("kFrameRange") or get("frame_range")
    requested = get("kRequestedSettings") or get("requested_settings")
    effective = get("kEffectiveSettings") or get("effective_settings")
    progress = get("kProgress") or get("progress")
    statistics = get("kStatistics") or get("statistics")
    return {
        "job_id": str(get("strJobId", get("job_id", ""))),
        "type": str(get("strType", get("type", ""))),
        "state": state,
        "status": state,
        "phase": str(get("strPhase", get("phase", ""))),
        "output_path": str(get("strOutputPath", get("output_path", ""))),
        "error": error or None,
        "output_size": _render_output_size_snapshot(output_size),
        "frame_range": _frame_range_snapshot(frame_range),
        "requested_settings": _render_settings_dto_snapshot(requested),
        "effective_settings": _render_settings_dto_snapshot(effective),
        "progress": _progress_snapshot(progress),
        "statistics": _statistics_snapshot(statistics),
        "cancellable": bool(get("bCancellable", get("cancellable", False))),
        "completion": bool(get("bCompletion", get("completion", False))),
    }


def _render_type_value(render_type):
    normalized = str(render_type or "").lower().replace("-", "_")
    names = {
        "video": "VIDEO",
        "image_sequence": "IMAGE_SEQUENCE",
        "sequence": "IMAGE_SEQUENCE",
    }
    constant_name = names.get(normalized)
    if constant_name is None:
        raise ValueError("render_type must be 'video' or 'image_sequence'")
    value = getattr(RLPy, constant_name, None)
    if value is None:
        value = {"VIDEO": 1, "IMAGE_SEQUENCE": 2}[constant_name]
    return value, normalized if normalized != "sequence" else "image_sequence"


def _frame_time(frame):
    fps = RLPy.RGlobal.GetFps()
    converter = getattr(fps, "IndexedFrameTime", None)
    if not callable(converter):
        raise RuntimeError("This iClone build cannot convert frames to time")
    return converter(frame)


def _render_time_range(args):
    start_frame = args.get("frame_start")
    end_frame = args.get("frame_end")
    if start_frame is not None or end_frame is not None:
        for name, value in (("frame_start", start_frame), ("frame_end", end_frame)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("{0} must be a non-negative integer".format(name))
        fps = RLPy.RGlobal.GetFps()
        if start_frame is None:
            start_frame = int(fps.GetFrameIndex(RLPy.RGlobal.GetStartTime()))
        if end_frame is None:
            end_frame = int(fps.GetFrameIndex(RLPy.RGlobal.GetEndTime()))
        if end_frame <= start_frame:
            raise ValueError("frame_end must be greater than frame_start")
        return _frame_time(start_frame), _frame_time(end_frame)
    return RLPy.RGlobal.GetStartTime(), RLPy.RGlobal.GetEndTime()


def _validate_render_output_path(output_path, required):
    if output_path is None or output_path == "":
        if required:
            raise ValueError("output_path must be a non-empty string")
        return None
    if not isinstance(output_path, str) or not output_path:
        raise ValueError("output_path must be a non-empty string")
    output_path = os.path.normpath(output_path)
    if not os.path.isabs(output_path):
        raise ValueError("output_path must be an absolute path")
    if not os.path.isdir(os.path.dirname(output_path)):
        raise ValueError("output_path parent directory does not exist")
    return output_path


def _start_native_render(args, render_type):
    native_start = getattr(RLPy.RGlobal, "StartRender", None)
    if not callable(native_start):
        raise RuntimeError("This iClone build does not expose native render jobs")
    type_value, normalized_type = _render_type_value(render_type)
    output_path = _validate_render_output_path(
        args.get("output_path"), normalized_type == "image_sequence"
    )
    start_time, end_time = _render_time_range(args)
    job = native_start(type_value, start_time, end_time, output_path or "")
    snapshot = _render_job_snapshot(job)
    snapshot["requested_render_type"] = normalized_type
    return snapshot


def get_render_output_size(_args):
    return _render_output_size_snapshot()


def set_render_output_size(args):
    width = args.get("width")
    height = args.get("height")
    if isinstance(width, bool) or not isinstance(width, int) or width <= 0:
        raise ValueError("width must be a positive integer")
    if isinstance(height, bool) or not isinstance(height, int) or height <= 0:
        raise ValueError("height must be a positive integer")

    export_type = args.get("export_type", args.get("render_type"))
    if export_type is not None:
        export_type = str(export_type).lower()
        export_type_values = {
            "image": getattr(RLPy, "IMAGE", 0),
            "video": getattr(RLPy, "VIDEO", 1),
            "image_sequence": getattr(RLPy, "IMAGE_SEQUENCE", 2),
            "sequence": getattr(RLPy, "IMAGE_SEQUENCE", 2),
            "audio": getattr(RLPy, "AUDIO", 3),
        }
        if export_type not in export_type_values:
            raise ValueError("export_type must be image, video, image_sequence, or audio")
        type_setter = getattr(RLPy.RGlobal, "SetRenderExportType", None)
        if not callable(type_setter):
            raise RuntimeError("This iClone build does not expose render export type setters")
        type_setter(export_type_values[export_type])

    setter = getattr(RLPy.RGlobal, "SetRenderOutputSize", None)
    if not callable(setter):
        raise RuntimeError("This iClone build does not expose render output setters")
    previous = get_render_output_size({})
    result = setter(width, height)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not set the render output size")
    effective = get_render_output_size({})
    if effective["width"] != width or effective["height"] != height:
        raise RuntimeError("iClone did not apply the requested render output size")
    return {
        "requested": {"width": width, "height": height},
        "effective": effective,
        "changed": previous != effective,
        "readback": effective,
    }


def get_render_frame_range(args):
    type_value, normalized_type = _render_type_value(args.get("render_type", "video"))
    getter = getattr(RLPy.RGlobal, "GetRenderFrameRange", None)
    if callable(getter):
        return {
            "render_type": normalized_type,
            "frame_range": _frame_range_snapshot(getter(type_value)),
        }
    fps = RLPy.RGlobal.GetFps()
    start = int(fps.GetFrameIndex(RLPy.RGlobal.GetStartTime()))
    end = int(fps.GetFrameIndex(RLPy.RGlobal.GetEndTime()))
    return {
        "render_type": normalized_type,
        "frame_range": {
            "start_frame": start,
            "end_frame": end,
            "frame_count": end - start + 1,
        },
    }


def get_viewport_samples(_args):
    getter = getattr(RLPy.RScene, "GetViewportSamples", None)
    if callable(getter):
        preview = int(getter(0))
        final = int(getter(1))
    else:
        getter = getattr(RLPy.RScene, "GetPathtracerRenderSettings", None)
        if not callable(getter):
            raise RuntimeError("This iClone build does not expose viewport samples")
        preview = int(_dto_member(getter(0), "nAccumulationTarget", 0))
        final = int(_dto_member(getter(1), "nAccumulationTarget", 0))
    active = 0
    settings_getter = getattr(RLPy.RGlobal, "GetRenderSettings", None)
    if callable(settings_getter):
        active = int(_dto_member(settings_getter(), "nActiveRenderMode", 0))
    return {
        "preview": preview,
        "final": final,
        "active_render_mode": active,
        "counters_separate": True,
    }


def set_viewport_samples(args):
    value = args.get("sample_count", args.get("value"))
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("sample_count must be a non-negative integer")
    mode = args.get("render_mode", args.get("mode"))
    if mode is None:
        settings_getter = getattr(RLPy.RGlobal, "GetRenderSettings", None)
        active = _dto_member(settings_getter(), "nActiveRenderMode", 0) if callable(settings_getter) else 0
        mode = int(active)
    elif isinstance(mode, str):
        mode = {"preview": 0, "final": 1}.get(mode.lower())
    if isinstance(mode, bool) or not isinstance(mode, int) or mode not in (0, 1):
        raise ValueError("render_mode must be preview/0 or final/1")
    setter = getattr(RLPy.RScene, "SetViewportSamples", None)
    if not callable(setter):
        setter = getattr(RLPy.RScene, "SetPathtracerAccumulationTarget", None)
    if not callable(setter):
        raise RuntimeError("This iClone build does not expose viewport sample setters")
    previous = get_viewport_samples({})
    result = setter(mode, value)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not set viewport samples")
    readback = get_viewport_samples({})
    effective = readback["preview"] if mode == 0 else readback["final"]
    if effective != value:
        raise RuntimeError("iClone did not apply the requested viewport sample count")
    return {
        "requested": {"render_mode": mode, "sample_count": value},
        "effective": effective,
        "changed": (previous["preview"] if mode == 0 else previous["final"]) != effective,
        "readback": readback,
    }


def get_render_progress(args):
    getter = getattr(RLPy.RGlobal, "GetRenderProgress", None)
    if not callable(getter):
        raise RuntimeError("This iClone build does not expose render progress")
    result = _progress_snapshot(getter())
    if args.get("include_statistics"):
        result["statistics"] = get_render_statistics({})
    return result


def get_render_statistics(_args):
    getter = getattr(RLPy.RGlobal, "GetRenderStatistics", None)
    if not callable(getter):
        raise RuntimeError("This iClone build does not expose render statistics")
    return _statistics_snapshot(getter())


def start_render(args):
    render_type = args.get("render_type", args.get("type"))
    if render_type is None:
        raise ValueError("render_type is required")
    return _start_native_render(args, render_type)


def get_render_job(args):
    job_id = args.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        raise ValueError("job_id must be a non-empty string")
    getter = getattr(RLPy.RGlobal, "GetRenderJob", None)
    if not callable(getter):
        raise RuntimeError("This iClone build does not expose render jobs")
    return _render_job_snapshot(getter(job_id))


def _render_settings_snapshot():
    output_size = _render_output_size_snapshot()
    render_system = RLPy.RGlobal.GetRenderSystem()
    debug_view = int(RLPy.RScene.GetPathtracerDebugView())
    debug_name = (
        _PATH_TRACER_DEBUG_VIEWS[debug_view]
        if 0 <= debug_view < len(_PATH_TRACER_DEBUG_VIEWS)
        else "unknown"
    )
    settings = _render_settings_dto_snapshot(
        RLPy.RGlobal.GetRenderSettings()
        if callable(getattr(RLPy.RGlobal, "GetRenderSettings", None))
        else None
    )
    result = {
        "width": output_size["width"],
        "height": output_size["height"],
        "output_size": output_size,
        "render_system": _render_system_name(render_system),
        "render_system_value": _enum_value(render_system),
        "pathtracer_debug_view": {
            "index": debug_view,
            "name": debug_name,
            "supported": debug_name != "unknown",
        },
        "note": "Other render options use the current iClone project settings.",
    }
    if settings is not None:
        result["render_settings"] = settings
        result["active_render_mode"] = settings["active_render_mode"]
        result["preview"] = settings["preview"]
        result["final"] = settings["final"]
        result["motion_blur"] = settings["motion_blur"]
    return result


def get_render_settings(_args):
    """Return output size plus the public RTX state exposed by RLPy."""
    return _render_settings_snapshot()


def _ibl_settings_snapshot(component=None):
    component = component or RLPy.RGlobal.GetVisualSettingComponent()
    return {
        "ibl_enabled": bool(component.IsIBLEnable()),
        "sync_sky_image": bool(component.IsIBLSyncSkyImage()),
        "sync_sky_orientation": bool(component.IsIBLSyncSkyOrientation()),
    }


def get_ibl_settings(_args):
    """Return the public IBL state exposed by RLPy."""
    return _ibl_settings_snapshot()


def set_ibl(args):
    """Load an IBL image and/or update its public visual-setting flags."""
    component = RLPy.RGlobal.GetVisualSettingComponent()
    image_path = args.get("image_path")
    response = {}
    if image_path is not None:
        if not isinstance(image_path, str) or not image_path:
            raise ValueError("image_path must be a non-empty string.")
        image_path = os.path.normpath(image_path)
        if not os.path.isabs(image_path) or not os.path.isfile(image_path):
            raise ValueError("image_path must be an existing absolute file path.")
        result = component.LoadIBLImage(image_path)
        if result != RLPy.RStatus.Success:
            raise RuntimeError("iClone could not load the IBL image")
        response["loaded_image_path"] = image_path

    for argument, setter in (
        ("sync_sky_image", component.SetIBLSyncSkyImage),
        ("sync_sky_orientation", component.SetIBLSyncSkyOrientation),
        ("enabled", component.SetIBLEnable),
    ):
        value = args.get(argument)
        if value is None:
            continue
        result = setter(bool(value))
        if result != RLPy.RStatus.Success:
            raise RuntimeError("iClone could not set IBL {0}".format(argument))

    response.update(_ibl_settings_snapshot(component))
    return response


def set_render_system(args):
    system = str(args.get("system", "")).lower()
    constants = {
        "dx11": getattr(RLPy, "ERenderSystem_DX11", None),
        "dx12": getattr(RLPy, "ERenderSystem_DX12", None),
    }
    if system not in constants or constants[system] is None:
        raise ValueError("system must be 'dx11' or 'dx12'")
    if _render_system_name(RLPy.RGlobal.GetRenderSystem()) == system:
        return _render_settings_snapshot()
    result = RLPy.RGlobal.SwitchRenderSystem(constants[system])
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not switch render system")
    _restart_mcp_listener()
    return _render_settings_snapshot()


def _restart_mcp_listener():
    try:
        from PySide2 import QtCore
        import main

        plugin = getattr(main, "_plugin", None)
        if plugin is None:
            return

        def restart():
            try:
                plugin._start(show_error=False)
            except Exception:
                pass

        QtCore.QTimer.singleShot(1000, restart)
    except Exception:
        pass


def _new_transition_id():
    global _TRANSITION_SEQUENCE
    _TRANSITION_SEQUENCE += 1
    return "render-system-{0}".format(_TRANSITION_SEQUENCE)


def _transition_elapsed(job):
    if job["state"] in ("completed", "failed", "cancelled"):
        return job["elapsed_ms"]
    return int((time.monotonic() - job["started_at"]) * 1000)


def _transition_snapshot(job):
    result = {
        key: value
        for key, value in job.items()
        if key not in {"started_at", "timer"}
    }
    result["elapsed_ms"] = _transition_elapsed(job)
    result["cancellable"] = job["state"] in ("queued", "waiting_for_dialog")
    return result


def _transition_dialogs():
    try:
        from iclone_mcp_tool_diagnostics import get_modal_dialogs

        return get_modal_dialogs({}).get("dialogs", [])
    except Exception:
        return []


def _run_render_system_transition(job_id):
    job = _TRANSITION_JOBS.get(job_id)
    if job is None or job["state"] in ("cancelled", "cancel_requested"):
        return

    job["state"] = "waiting_for_dialog"
    job["phase"] = "waiting_for_dialog"
    dialogs = _transition_dialogs()
    if dialogs:
        job["dialogs"] = dialogs
        try:
            from PySide2 import QtCore

            job["timer"] = QtCore.QTimer.singleShot(
                50, lambda transition_id=job_id: _run_render_system_transition(transition_id)
            )
            return
        except (ImportError, AttributeError):
            pass

    job["state"] = "switching"
    job["phase"] = "switching"
    job["cancellable"] = False
    try:
        result = RLPy.RGlobal.SwitchRenderSystem(job["requested_system_value"])
        if result != RLPy.RStatus.Success:
            raise RuntimeError("iClone could not switch render system")
        job["current_system"] = _render_system_name(RLPy.RGlobal.GetRenderSystem())
        _restart_mcp_listener()
        job["phase"] = "completed"
        job["state"] = "completed"
        job["completion"] = True
    except Exception as error:
        job["phase"] = "failed"
        job["state"] = "failed"
        job["completion"] = False
        job["error"] = str(error)
    job["elapsed_ms"] = int((time.monotonic() - job["started_at"]) * 1000)


def start_render_system_transition(args):
    system = str(args.get("system", "")).lower()
    constants = {
        "dx11": getattr(RLPy, "ERenderSystem_DX11", None),
        "dx12": getattr(RLPy, "ERenderSystem_DX12", None),
    }
    if system not in constants or constants[system] is None:
        raise ValueError("system must be 'dx11' or 'dx12'")
    if any(job["state"] in ("queued", "waiting_for_dialog", "switching", "cancel_requested") for job in _TRANSITION_JOBS.values()):
        raise RuntimeError("A render-system transition is already running")

    current = _render_system_name(RLPy.RGlobal.GetRenderSystem())
    job = {
        "job_id": _new_transition_id(),
        "requested_system": system,
        "requested_system_value": constants[system],
        "current_system": current,
        "state": "queued",
        "phase": "queued",
        "completion": False,
        "error": None,
        "dialogs": [],
        "elapsed_ms": 0,
        "started_at": time.monotonic(),
        "cancellable": True,
    }
    _TRANSITION_JOBS[job["job_id"]] = job
    try:
        from PySide2 import QtCore

        job["timer"] = QtCore.QTimer.singleShot(
            0, lambda job_id=job["job_id"]: _run_render_system_transition(job_id)
        )
    except (ImportError, AttributeError):
        _run_render_system_transition(job["job_id"])
    return _transition_snapshot(job)


def get_render_system_transition(args):
    job_id = args.get("job_id")
    job = _TRANSITION_JOBS.get(job_id)
    if job is None:
        raise ValueError("Unknown render-system transition job: {0}".format(job_id))
    return _transition_snapshot(job)


def cancel_render_system_transition(args):
    job_id = args.get("job_id")
    job = _TRANSITION_JOBS.get(job_id)
    if job is None:
        raise ValueError("Unknown render-system transition job: {0}".format(job_id))
    if job["state"] in ("queued", "waiting_for_dialog"):
        job["state"] = "cancelled"
        job["phase"] = "cancelled"
        job["completion"] = False
        job["cancellable"] = False
    elif job["state"] == "switching":
        job["state"] = "cancel_requested"
        job["phase"] = "cancel_requested"
        job["cancellable"] = False
    return _transition_snapshot(job)


def get_pathtracer_debug_view(_args):
    index = int(RLPy.RScene.GetPathtracerDebugView())
    return {
        "index": index,
        "name": _PATH_TRACER_DEBUG_VIEWS[index]
        if 0 <= index < len(_PATH_TRACER_DEBUG_VIEWS)
        else "unknown",
        "options": list(_PATH_TRACER_DEBUG_VIEWS),
        "views": get_pathtracer_debug_views({})["views"],
    }


def get_pathtracer_debug_views(_args):
    return {
        "views": [
            {"index": index, "name": name, "supported": True, "reason": None}
            for index, name in enumerate(_PATH_TRACER_DEBUG_VIEWS)
        ]
        + [dict(item, index=None) for item in _OPTIONAL_DEBUG_VIEWS],
        "count": len(_PATH_TRACER_DEBUG_VIEWS),
    }


def set_pathtracer_debug_view(args):
    if args.get("name") is not None:
        name = args["name"]
        if name not in _PATH_TRACER_DEBUG_VIEW_INDEX:
            raise ValueError("Unknown path-tracer debug view: {0}".format(name))
        index = _PATH_TRACER_DEBUG_VIEW_INDEX[name]
    elif args.get("index") is not None:
        index = int(args["index"])
        if index < 0 or index >= len(_PATH_TRACER_DEBUG_VIEWS):
            raise ValueError("index is outside the path-tracer debug-view range")
    else:
        raise ValueError("Provide name or index")

    result = RLPy.RScene.SetPathtracerDebugView(index)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not set the path-tracer debug view")
    return get_pathtracer_debug_view({})


def render_image(args):
    """Render one image with the current iClone project settings."""
    if args.get("passes"):
        return render_multi_pass(args)
    if args.get("confirm") != "RENDER_IMAGE_WITH_CURRENT_SETTINGS":
        raise ValueError("Set confirm to RENDER_IMAGE_WITH_CURRENT_SETTINGS to render")
    output_path = args.get("output_path")
    if not isinstance(output_path, str) or not output_path:
        raise ValueError("output_path must be a non-empty string.")
    output_path = os.path.normpath(output_path)
    if not os.path.isabs(output_path):
        raise ValueError("output_path must be an absolute path.")
    parent = os.path.dirname(output_path)
    if not os.path.isdir(parent):
        raise ValueError("output_path parent directory does not exist.")
    result = RLPy.RGlobal.RenderImage(output_path)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not render the image")
    return {"status": "completed", "output_path": output_path}


def render_multi_pass(args):
    """Render a small ordered pass set and restore the original debug view."""
    if args.get("confirm") != "RENDER_MULTI_PASS_WITH_CURRENT_SETTINGS":
        raise ValueError("Set confirm to RENDER_MULTI_PASS_WITH_CURRENT_SETTINGS to render")
    output_dir = args.get("output_dir")
    if not isinstance(output_dir, str) or not output_dir:
        raise ValueError("output_dir must be a non-empty string.")
    output_dir = os.path.normpath(output_dir)
    if not os.path.isabs(output_dir) or not os.path.isdir(output_dir):
        raise ValueError("output_dir must be an existing absolute directory.")
    passes = args.get("passes")
    if not isinstance(passes, list) or not passes:
        raise ValueError("passes must be a non-empty list")

    original_index = int(RLPy.RScene.GetPathtracerDebugView())
    outputs = []
    try:
        for item in passes:
            if not isinstance(item, dict):
                raise ValueError("Each pass must be an object")
            name = item.get("name")
            debug_view = item.get("debug_view")
            file_name = item.get("file_name")
            if debug_view not in _PATH_TRACER_DEBUG_VIEW_INDEX:
                raise ValueError("Unknown path-tracer debug view: %s" % debug_view)
            if not isinstance(file_name, str) or not file_name or os.path.basename(file_name) != file_name:
                raise ValueError("file_name must be a simple file name")
            output_path = os.path.join(output_dir, file_name)
            if os.path.commonpath([output_dir, output_path]) != output_dir:
                raise ValueError("file_name escapes output_dir")
            result = RLPy.RScene.SetPathtracerDebugView(_PATH_TRACER_DEBUG_VIEW_INDEX[debug_view])
            if result != RLPy.RStatus.Success:
                raise RuntimeError("iClone could not set pass %s" % name)
            result = RLPy.RGlobal.RenderImage(output_path)
            if result != RLPy.RStatus.Success:
                raise RuntimeError("iClone could not render pass %s" % name)
            outputs.append({"name": name, "debug_view": debug_view, "output_path": output_path})
    finally:
        RLPy.RScene.SetPathtracerDebugView(original_index)
    return {"status": "completed", "passes": outputs, "restored_debug_view": original_index}


def render_video(args):
    """Start iClone's video rendering with its already configured project settings."""
    if args.get("confirm") != "RENDER_VIDEO_WITH_CURRENT_SETTINGS":
        raise ValueError("Set confirm to RENDER_VIDEO_WITH_CURRENT_SETTINGS to start rendering")

    if callable(getattr(RLPy.RGlobal, "StartRender", None)):
        response = _start_native_render(args, "video")
        response["status"] = "started" if response["state"] in ("queued", "running") else response["state"]
        response["message"] = "iClone queued video rendering with the current project frame range and render settings."
        return response

    start_time, end_time = _render_time_range(args)
    output_path = _validate_render_output_path(args.get("output_path"), False)
    result = (
        RLPy.RGlobal.RenderVideo(start_time, end_time, output_path)
        if output_path is not None
        else RLPy.RGlobal.RenderVideo(start_time, end_time)
    )
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not start video rendering")
    response = {
        "status": "started",
        "message": "iClone started rendering with the current project frame range and render settings.",
    }
    if output_path is not None:
        response["output_path"] = output_path
    return response


def render_image_sequence(args):
    """Start image-sequence rendering with the current project settings."""
    if args.get("confirm") != "RENDER_IMAGE_SEQUENCE_WITH_CURRENT_SETTINGS":
        raise ValueError("Set confirm to RENDER_IMAGE_SEQUENCE_WITH_CURRENT_SETTINGS to start rendering")
    if callable(getattr(RLPy.RGlobal, "StartRender", None)):
        response = _start_native_render(args, "image_sequence")
        response["status"] = "started" if response["state"] in ("queued", "running") else response["state"]
        response["message"] = "iClone queued image-sequence rendering with the current project frame range and render settings."
        return response

    output_path = _validate_render_output_path(args.get("output_path"), True)
    start_time, end_time = _render_time_range(args)
    result = RLPy.RGlobal.RenderImageSequence(start_time, end_time, output_path)
    if result == RLPy.RStatus.Safe:
        return {"status": "cancelled", "output_path": output_path}
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not render the image sequence")
    return {"status": "completed", "output_path": output_path}


def cancel_render(args):
    """Request cooperative cancellation through the native render-job API."""
    job_id = args.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        raise ValueError("job_id must be a non-empty string")
    cancel = getattr(RLPy.RGlobal, "CancelRender", None)
    if not callable(cancel):
        raise RuntimeError("This iClone build does not expose native render cancellation")
    return _render_job_snapshot(cancel(job_id))


def set_render_settings(args):
    """Route output-size and/or viewport-sample writes into the existing setters."""
    results = {}
    if "width" in args or "height" in args:
        results["output_size"] = set_render_output_size(args)
    if "sample_count" in args or "value" in args:
        results["viewport_samples"] = set_viewport_samples(args)
    if not results:
        raise ValueError("Provide width/height and/or sample_count (or value)")
    return results


def render_job(args):
    action = (args.get("action") or "").lower()
    if action == "get":
        return get_render_job(args)
    if action == "cancel":
        return cancel_render(args)
    if action == "start":
        confirm = args.get("confirm")
        if confirm == "RENDER_VIDEO_WITH_CURRENT_SETTINGS":
            return render_video(args)
        if confirm == "RENDER_IMAGE_SEQUENCE_WITH_CURRENT_SETTINGS":
            return render_image_sequence(args)
        return start_render(args)
    raise ValueError("action must be one of: start, get, cancel")


def render_system(args):
    action = (args.get("action") or "").lower()
    if action == "set":
        return set_render_system(args)
    if action == "start":
        return start_render_system_transition(args)
    if action == "get":
        return get_render_system_transition(args)
    if action == "cancel":
        return cancel_render_system_transition(args)
    raise ValueError("action must be one of: set, start, get, cancel")


def pathtracer_debug_view(args):
    action = (args.get("action") or "get").lower()
    if action == "get":
        return get_pathtracer_debug_view(args)
    if action == "list":
        return get_pathtracer_debug_views(args)
    if action == "set":
        return set_pathtracer_debug_view(args)
    raise ValueError("action must be one of: get, list, set")


def ibl(args):
    action = (args.get("action") or "get").lower()
    if action == "get":
        return get_ibl_settings(args)
    if action == "set":
        return set_ibl(args)
    raise ValueError("action must be one of: get, set")


def register(registry):
    registry["get_render_settings"] = {
        "handler": get_render_settings,
        "main_thread": True,
        "read_only": True,
        "description": "Lit la taille de sortie effective et les réglages path-tracer Preview/Final.",
        "inputSchema": {"type": "object", "properties": {}},
    }
    registry["set_render_settings"] = {
        "handler": set_render_settings,
        "main_thread": True,
        "description": "Set render output size and/or viewport sample counts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "width": {"type": "integer", "minimum": 1},
                "height": {"type": "integer", "minimum": 1},
                "export_type": {"type": "string", "enum": ["image", "video", "image_sequence", "audio"]},
                "render_type": {"type": "string", "enum": ["image", "video", "image_sequence", "audio"]},
                "sample_count": {"type": "integer", "minimum": 0},
                "value": {"type": "integer", "minimum": 0},
                "render_mode": {"type": "string", "enum": ["preview", "final"]},
                "mode": {"type": "string", "enum": ["preview", "final"]},
            },
        },
    }
    registry["render_job"] = {
        "handler": render_job,
        "main_thread": True,
        "destructive": True,
        "description": "Start, poll, or cancel a native render job. For start: confirm RENDER_VIDEO... or RENDER_IMAGE_SEQUENCE... routes to those APIs; otherwise start_render.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["start", "get", "cancel"]},
                "job_id": {"type": "string"},
                "confirm": {"type": "string"},
                "render_type": {"type": "string", "enum": ["video", "image_sequence"]},
                "type": {"type": "string", "enum": ["video", "image_sequence"]},
                "output_path": {"type": "string"},
                "frame_start": {"type": "integer", "minimum": 0},
                "frame_end": {"type": "integer", "minimum": 0},
            },
            "required": ["action"],
        },
    }
    registry["render_system"] = {
        "handler": render_system,
        "main_thread": True,
        "description": "Switch render system (set) or manage an observable DX11/DX12 transition (start|get|cancel).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["set", "start", "get", "cancel"]},
                "system": {"type": "string", "enum": ["dx11", "dx12"]},
                "job_id": {"type": "string"},
            },
            "required": ["action"],
        },
    }
    registry["pathtracer_debug_view"] = {
        "handler": pathtracer_debug_view,
        "main_thread": True,
        "description": "Get, list, or set the RTX path-tracer debug/render pass view.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["get", "list", "set"]},
                "name": {"type": "string", "enum": list(_PATH_TRACER_DEBUG_VIEWS)},
                "index": {"type": "integer", "minimum": 0},
            },
            "required": ["action"],
        },
    }
    registry["get_render_progress"] = {
        "handler": get_render_progress,
        "main_thread": True,
        "read_only": True,
        "description": "Lit la progression native du rendu. Set include_statistics to also return render statistics.",
        "inputSchema": {
            "type": "object",
            "properties": {"include_statistics": {"type": "boolean"}},
        },
    }
    registry["render_image"] = {
        "handler": render_image,
        "main_thread": True,
        "destructive": True,
        "description": "Render one image, or a multi-pass set when passes[] is provided. Keep the matching confirm token.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "output_path": {"type": "string"},
                "output_dir": {"type": "string"},
                "passes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "debug_view": {"type": "string", "enum": list(_PATH_TRACER_DEBUG_VIEWS)},
                            "file_name": {"type": "string"},
                        },
                        "required": ["name", "debug_view", "file_name"],
                    },
                },
                "confirm": {"type": "string"},
            },
            "required": ["confirm"],
        },
    }
    registry["ibl"] = {
        "handler": ibl,
        "main_thread": True,
        "description": "Get or set IBL visual-setting state (action get|set).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["get", "set"]},
                "image_path": {"type": "string"},
                "enabled": {"type": "boolean"},
                "sync_sky_image": {"type": "boolean"},
                "sync_sky_orientation": {"type": "boolean"},
            },
            "required": ["action"],
        },
    }

    # Legacy wrappers kept for bridge dispatch; not advertised to MCP clients.
    _hidden = {"advertise": False, "main_thread": True}
    registry["get_render_output_size"] = dict(
        _hidden, handler=get_render_output_size, read_only=True,
        description="Lit la taille de sortie effective du rendu.",
        inputSchema={"type": "object", "properties": {}},
    )
    registry["set_render_output_size"] = dict(
        _hidden, handler=set_render_output_size,
        description="Règle la taille de sortie du rendu et retourne le readback effectif.",
        inputSchema={
            "type": "object",
            "properties": {
                "width": {"type": "integer", "minimum": 1},
                "height": {"type": "integer", "minimum": 1},
                "export_type": {"type": "string", "enum": ["image", "video", "image_sequence", "audio"]},
                "render_type": {"type": "string", "enum": ["image", "video", "image_sequence", "audio"]},
            },
            "required": ["width", "height"],
        },
    )
    registry["get_render_frame_range"] = dict(
        _hidden, handler=get_render_frame_range, read_only=True,
        description="Lit la plage de frames effective d'une vidéo ou d'une séquence.",
        inputSchema={"type": "object", "properties": {"render_type": {"type": "string", "enum": ["video", "image_sequence"]}}},
    )
    registry["get_viewport_samples"] = dict(
        _hidden, handler=get_viewport_samples, read_only=True,
        description="Lit séparément les compteurs d'échantillons Preview et Final.",
        inputSchema={"type": "object", "properties": {}},
    )
    registry["set_viewport_samples"] = dict(
        _hidden, handler=set_viewport_samples,
        description="Règle le compteur d'échantillons Preview ou Final et retourne le readback.",
        inputSchema={
            "type": "object",
            "properties": {
                "sample_count": {"type": "integer", "minimum": 0},
                "value": {"type": "integer", "minimum": 0},
                "render_mode": {"type": "string", "enum": ["preview", "final"]},
                "mode": {"type": "string", "enum": ["preview", "final"]},
            },
            "oneOf": [{"required": ["sample_count"]}, {"required": ["value"]}],
        },
    )
    registry["get_render_statistics"] = dict(
        _hidden, handler=get_render_statistics, read_only=True,
        description="Lit les statistiques natives du rendu et son état de complétion.",
        inputSchema={"type": "object", "properties": {}},
    )
    registry["start_render"] = dict(
        _hidden, handler=start_render, destructive=True,
        description="Démarre un job natif asynchrone de vidéo ou de séquence d'images.",
        inputSchema={
            "type": "object",
            "properties": {
                "render_type": {"type": "string", "enum": ["video", "image_sequence"]},
                "type": {"type": "string", "enum": ["video", "image_sequence"]},
                "output_path": {"type": "string"},
                "frame_start": {"type": "integer", "minimum": 0},
                "frame_end": {"type": "integer", "minimum": 0},
            },
            "oneOf": [{"required": ["render_type"]}, {"required": ["type"]}],
        },
    )
    registry["get_render_job"] = dict(
        _hidden, handler=get_render_job, read_only=True,
        description="Lit l'état, la progression et les statistiques d'un job de rendu natif.",
        inputSchema={"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]},
    )
    registry["get_ibl_settings"] = dict(
        _hidden, handler=get_ibl_settings, read_only=True,
        description="Lit l'état IBL courant exposé par iClone.",
        inputSchema={"type": "object", "properties": {}},
    )
    registry["set_ibl"] = dict(
        _hidden, handler=set_ibl,
        description="Charge une image IBL et règle ses options publiques iClone.",
        inputSchema={
            "type": "object",
            "properties": {
                "image_path": {"type": "string"},
                "enabled": {"type": "boolean"},
                "sync_sky_image": {"type": "boolean"},
                "sync_sky_orientation": {"type": "boolean"},
            },
        },
    )
    registry["set_render_system"] = dict(
        _hidden, handler=set_render_system,
        description="Bascule le render system iClone entre DX11 et DX12/RTX.",
        inputSchema={
            "type": "object",
            "properties": {"system": {"type": "string", "enum": ["dx11", "dx12"]}},
            "required": ["system"],
        },
    )
    registry["start_render_system_transition"] = dict(
        _hidden, handler=start_render_system_transition,
        description="Démarre une transition render system observable et annulable aux points sûrs.",
        inputSchema={
            "type": "object",
            "properties": {"system": {"type": "string", "enum": ["dx11", "dx12"]}},
            "required": ["system"],
        },
    )
    registry["get_render_system_transition"] = dict(
        _hidden, handler=get_render_system_transition, read_only=True,
        description="Lit l'état d'une transition render system.",
        inputSchema={"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]},
    )
    registry["cancel_render_system_transition"] = dict(
        _hidden, handler=cancel_render_system_transition, destructive=True,
        description="Demande l'annulation coopérative d'une transition render system.",
        inputSchema={"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]},
    )
    registry["get_pathtracer_debug_view"] = dict(
        _hidden, handler=get_pathtracer_debug_view, read_only=True,
        description="Lit le render pass/debug view RTX courant et les options disponibles.",
        inputSchema={"type": "object", "properties": {}},
    )
    registry["get_pathtracer_debug_views"] = dict(
        _hidden, handler=get_pathtracer_debug_views, read_only=True,
        description="Liste le catalogue RTX canonical et les vues optionnelles non supportées.",
        inputSchema={"type": "object", "properties": {}},
    )
    registry["set_pathtracer_debug_view"] = dict(
        _hidden, handler=set_pathtracer_debug_view,
        description="Sélectionne un render pass/debug view RTX par nom ou index.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "enum": list(_PATH_TRACER_DEBUG_VIEWS)},
                "index": {"type": "integer", "minimum": 0},
            },
        },
    )
    registry["render_multi_pass"] = dict(
        _hidden, handler=render_multi_pass, destructive=True,
        description="Rend une liste ordonnée de passes dans un dossier et restaure le pass original.",
        inputSchema={
            "type": "object",
            "properties": {
                "output_dir": {"type": "string"},
                "passes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "debug_view": {"type": "string", "enum": list(_PATH_TRACER_DEBUG_VIEWS)},
                            "file_name": {"type": "string"},
                        },
                        "required": ["name", "debug_view", "file_name"],
                    },
                },
                "confirm": {"type": "string", "description": "Valeur exacte : RENDER_MULTI_PASS_WITH_CURRENT_SETTINGS"},
            },
            "required": ["output_dir", "passes", "confirm"],
        },
    )
    registry["render_video"] = dict(
        _hidden, handler=render_video, destructive=True,
        description="Met en file un rendu vidéo natif avec les réglages actuels. Requiert une confirmation explicite.",
        inputSchema={
            "type": "object",
            "properties": {
                "confirm": {"type": "string", "description": "Valeur exacte : RENDER_VIDEO_WITH_CURRENT_SETTINGS"},
                "output_path": {"type": "string"},
                "frame_start": {"type": "integer", "minimum": 0},
                "frame_end": {"type": "integer", "minimum": 0},
            },
            "required": ["confirm"],
        },
    )
    registry["render_image_sequence"] = dict(
        _hidden, handler=render_image_sequence, destructive=True,
        description="Met en file un rendu natif de séquence d'images avec les réglages actuels. Requiert une confirmation explicite.",
        inputSchema={
            "type": "object",
            "properties": {
                "confirm": {"type": "string", "description": "Valeur exacte : RENDER_IMAGE_SEQUENCE_WITH_CURRENT_SETTINGS"},
                "output_path": {"type": "string"},
                "frame_start": {"type": "integer", "minimum": 0},
                "frame_end": {"type": "integer", "minimum": 0},
            },
            "required": ["confirm", "output_path"],
        },
    )
    registry["cancel_render"] = dict(
        _hidden, handler=cancel_render, destructive=True,
        description="Demande l'annulation coopérative d'un job de rendu natif.",
        inputSchema={"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]},
    )
