import math
import os
import time

import RLPy

try:
    import RLPy2
except ImportError:
    RLPy2 = None


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
    render_options = _render_export_options_snapshot(required=False)
    if render_options is not None:
        result["render_options"] = render_options
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


_IBL_DYNAMIC_FIELDS = {
    "sky_brightness": "SetIBLSkyBrightness",
    "sun_brightness": "SetIBLSunBrightness",
    "clouds_movement_speed": "SetIBLCloudsMovementSpeed",
    "time_of_day_movement_speed": "SetIBLTimeOfDayMovementSpeed",
    "sun_time_of_day_offset": "SetIBLSunTimeOfDayOffset",
    "sun_east_west_rotation": "SetIBLSunEastWestRotation",
    "sun_angular_diameter_deg": "SetIBLSunAngularDiameterDeg",
    "cloud_density_offset": "SetIBLCloudDensityOffset",
    "cloud_transmittance": "SetIBLCloudTransmittance",
    "horizon_height": "SetIBLHorizonHeight",
    "horizon_blur": "SetIBLHorizonBlur",
    "lower_hemisphere_brightness": "SetIBLLowerHemisphereBrightness",
}
_BACKGROUND_DYNAMIC_FIELDS = {
    key: value.replace("SetIBL", "SetBackgroundIBL")
    for key, value in _IBL_DYNAMIC_FIELDS.items()
}
_BACKGROUND_MODE_NAMES = {
    "sync_light_settings": "SyncLightSettings",
    "ibl": "IBL",
    "dynamic_sky": "DynamicSky",
    "background_2d": "Background2D",
}


def _rpy2_environment_interfaces():
    try:
        import RLPy2

        edit = RLPy2.Edit.GetInterface()
        query = RLPy2.Query.GetInterface()
        file_api = RLPy2.File.GetInterface()
    except (ImportError, AttributeError) as error:
        raise RuntimeError("Environment APIs require the updated RLPy2 binding; rebuild and restart iClone.") from error
    if edit is None or query is None or file_api is None:
        raise RuntimeError("iClone RLPy2 environment interfaces are unavailable.")
    return RLPy2, edit, query, file_api


def _require_native_result(result, operation):
    is_error = getattr(result, "IsError", None)
    if (callable(is_error) and is_error()) or (not callable(is_error) and not bool(result)):
        raise RuntimeError("iClone could not {0}".format(operation))


def _validated_ibl_path(args):
    image_path = args.get("image_path")
    if image_path is None:
        return None
    if not isinstance(image_path, str) or not image_path:
        raise ValueError("image_path must be a non-empty string.")
    image_path = os.path.normpath(image_path)
    if not os.path.isabs(image_path) or not os.path.isfile(image_path):
        raise ValueError("image_path must be an existing absolute file path.")
    return image_path


def _world_background_mode_name(rpy2, mode):
    enum_type = getattr(rpy2, "EWorldBackgroundMode", None)
    if enum_type is not None:
        for name, member in _BACKGROUND_MODE_NAMES.items():
            if mode == getattr(enum_type, member):
                return name
    value = str(mode).rsplit(".", 1)[-1].lower()
    return next((name for name, member in _BACKGROUND_MODE_NAMES.items() if member.lower() == value), value)


def _color_readback(color):
    def channel(*names):
        for name in names:
            value = getattr(color, name, None)
            if value is not None:
                return float(value() if callable(value) else value)
        return None

    return {"r": channel("Red", "R"), "g": channel("Green", "G"), "b": channel("Blue", "B")}


def _lighting_ibl_state(component=None):
    component = component or RLPy.RGlobal.GetVisualSettingComponent()
    state = dict(_ibl_settings_snapshot(component), target="lighting")
    try:
        rpy2, unused_edit, query, unused_file = _rpy2_environment_interfaces()
    except RuntimeError:
        return state
    enabled = bool(query.IBLEnabled())
    procedural_sky = bool(query.IBLProceduralSkyEnabled())
    state.update({
        "source": "dynamic_sky" if procedural_sky else ("ibl" if enabled else "ambient"),
        "image_path": str(query.IBLPath()),
        "strength": float(query.IBLStrength()),
        "procedural_sky_enabled": procedural_sky,
        "ambient_color": _color_readback(query.AmbientLightColor()),
        "ibl_clip_count": int(query.GetIBLClipCount()),
        "dynamic_sky": {
            "sky_brightness": float(query.IBLSkyBrightness()),
            "sun_brightness": float(query.IBLSunBrightness()),
            "clouds_movement_speed": float(query.IBLCloudsMovementSpeed()),
            "time_of_day_movement_speed": float(query.IBLTimeOfDayMovementSpeed()),
            "sun_time_of_day_offset": float(query.IBLSunTimeOfDayOffset()),
            "sun_east_west_rotation": float(query.IBLSunEastWestRotation()),
            "sun_angular_diameter_deg": float(query.IBLSunAngularDiameterDeg()),
            "cloud_density_offset": float(query.IBLCloudDensityOffset()),
            "cloud_transmittance": float(query.IBLCloudTransmittance()),
            "horizon_height": float(query.IBLHorizonHeight()),
            "horizon_blur": float(query.IBLHorizonBlur()),
            "lower_hemisphere_brightness": float(query.IBLLowerHemisphereBrightness()),
        },
    })
    return state


def _background_ibl_state():
    rpy2, unused_edit, query, unused_file = _rpy2_environment_interfaces()
    return {
        "target": "background",
        "background_mode": _world_background_mode_name(rpy2, query.GetWorldBackgroundMode()),
        "show_background": bool(query.ShowWorldBackground()),
        "enabled": bool(query.BackgroundIBLEnabled()),
        "light_source_enabled": bool(query.BackgroundIBLLightSourceEnabled()),
        "image_path": str(query.BackgroundIBLPath()),
        "strength": float(query.BackgroundIBLStrength()),
        "blur": float(query.BackgroundIBLBlur()),
        "procedural_sky_enabled": bool(query.BackgroundIBLProceduralSkyEnabled()),
        "ambient_color": _color_readback(query.BackgroundAmbientColor()),
        "ibl_clip_count": int(query.GetBackgroundIBLClipCount()),
        "dynamic_sky": {
            "sky_brightness": float(query.BackgroundIBLSkyBrightness()),
            "sun_brightness": float(query.BackgroundIBLSunBrightness()),
            "clouds_movement_speed": float(query.BackgroundIBLCloudsMovementSpeed()),
            "time_of_day_movement_speed": float(query.BackgroundIBLTimeOfDayMovementSpeed()),
            "sun_time_of_day_offset": float(query.BackgroundIBLSunTimeOfDayOffset()),
            "sun_east_west_rotation": float(query.BackgroundIBLSunEastWestRotation()),
            "sun_angular_diameter_deg": float(query.BackgroundIBLSunAngularDiameterDeg()),
            "cloud_density_offset": float(query.BackgroundIBLCloudDensityOffset()),
            "cloud_transmittance": float(query.BackgroundIBLCloudTransmittance()),
            "horizon_height": float(query.BackgroundIBLHorizonHeight()),
            "horizon_blur": float(query.BackgroundIBLHorizonBlur()),
            "lower_hemisphere_brightness": float(query.BackgroundIBLLowerHemisphereBrightness()),
        },
    }


def get_ibl_settings(args):
    """Return World Lighting or World Background IBL state."""
    target = (args.get("target") or "lighting").lower()
    if target == "background":
        return _background_ibl_state()
    if target != "lighting":
        raise ValueError("target must be lighting or background")
    return _lighting_ibl_state()


def _set_ibl_fields(edit, args, mapping, operation_prefix):
    for argument, method_name in mapping.items():
        if argument not in args:
            continue
        _require_native_result(
            getattr(edit, method_name)(float(args[argument]), True),
            "set {0} {1}".format(operation_prefix, argument),
        )


def _set_lighting_source(edit, source):
    source = str(source).lower()
    if source not in ("ambient", "ibl", "dynamic_sky"):
        raise ValueError("source must be ambient, ibl, or dynamic_sky")
    _require_native_result(edit.EnableIBL(source != "ambient", True), "set World Lighting source")
    _require_native_result(edit.SetIBLProceduralSkyEnabled(source == "dynamic_sky", True), "set Dynamic Sky source")


def _set_lighting_ibl(args):
    component = RLPy.RGlobal.GetVisualSettingComponent()
    image_path = _validated_ibl_path(args)
    response = {}
    needs_rpy2 = any(key in args for key in ("source", "strength", "procedural_sky_enabled")) or any(
        key in args for key in _IBL_DYNAMIC_FIELDS
    )
    rpy2 = edit = None
    if needs_rpy2:
        rpy2, edit, unused_query, unused_file = _rpy2_environment_interfaces()

    if "source" in args:
        _set_lighting_source(edit, args["source"])
    elif "enabled" in args and edit is not None:
        _require_native_result(edit.EnableIBL(bool(args["enabled"]), True), "set World Lighting IBL state")
    elif "enabled" in args:
        result = component.SetIBLEnable(bool(args["enabled"]))
        if result != RLPy.RStatus.Success:
            raise RuntimeError("iClone could not set IBL enabled")

    if "procedural_sky_enabled" in args:
        if edit is None:
            rpy2, edit, unused_query, unused_file = _rpy2_environment_interfaces()
        if bool(args["procedural_sky_enabled"]):
            _require_native_result(edit.EnableIBL(True, True), "enable Dynamic Sky")
        _require_native_result(
            edit.SetIBLProceduralSkyEnabled(bool(args["procedural_sky_enabled"]), True),
            "set Dynamic Sky state",
        )

    if image_path is not None:
        result = component.LoadIBLImage(image_path)
        if result != RLPy.RStatus.Success:
            raise RuntimeError("iClone could not load the World Lighting IBL image")
        response["loaded_image_path"] = image_path

    for argument, setter in (
        ("sync_sky_image", component.SetIBLSyncSkyImage),
        ("sync_sky_orientation", component.SetIBLSyncSkyOrientation),
    ):
        if argument in args:
            result = setter(bool(args[argument]))
            if result != RLPy.RStatus.Success:
                raise RuntimeError("iClone could not set IBL {0}".format(argument))

    if "strength" in args or any(key in args for key in _IBL_DYNAMIC_FIELDS):
        if edit is None:
            rpy2, edit, unused_query, unused_file = _rpy2_environment_interfaces()
    if "strength" in args:
        _require_native_result(edit.SetIBLStrength(float(args["strength"]), True), "set World Lighting IBL strength")
    _set_ibl_fields(edit, args, _IBL_DYNAMIC_FIELDS, "World Lighting") if any(
        key in args for key in _IBL_DYNAMIC_FIELDS
    ) else None

    response.update(get_ibl_settings({"target": "lighting"}))
    return response


def _set_background_ibl(args):
    rpy2, edit, unused_query, file_api = _rpy2_environment_interfaces()
    image_path = _validated_ibl_path(args)
    response = {}

    if "background_mode" in args:
        mode = str(args["background_mode"]).lower()
        mode_member = _BACKGROUND_MODE_NAMES.get(mode)
        enum_type = getattr(rpy2, "EWorldBackgroundMode", None)
        if mode_member is None or enum_type is None:
            raise ValueError("background_mode must be sync_light_settings, ibl, dynamic_sky, or background_2d")
        _require_native_result(
            edit.SetWorldBackgroundMode(getattr(enum_type, mode_member), True),
            "set World Background mode",
        )
        if mode in ("ibl", "dynamic_sky"):
            _require_native_result(edit.EnableBackgroundIBL(True, True), "enable World Background IBL")
            _require_native_result(
                edit.SetBackgroundIBLProceduralSkyEnabled(mode == "dynamic_sky", True),
                "set World Background Dynamic Sky state",
            )

    if image_path is not None:
        _require_native_result(
            file_api.LoadBackgroundIBLImage(image_path, True),
            "load World Background IBL image",
        )
        response["loaded_image_path"] = image_path

    if "enabled" in args:
        _require_native_result(edit.EnableBackgroundIBL(bool(args["enabled"]), True), "set World Background IBL enabled")
    if "light_source_enabled" in args:
        _require_native_result(
            edit.EnableBackgroundIBLLightSource(bool(args["light_source_enabled"]), True),
            "set World Background IBL light source",
        )
    if "show_background" in args:
        _require_native_result(edit.SetShowWorldBackground(bool(args["show_background"]), True), "set World Background visibility")
    if "strength" in args:
        _require_native_result(edit.SetBackgroundIBLStrength(float(args["strength"]), True), "set World Background IBL strength")
    if "blur" in args:
        _require_native_result(edit.SetBackgroundIBLBlur(float(args["blur"]), True), "set World Background IBL blur")
    if "procedural_sky_enabled" in args:
        _require_native_result(
            edit.SetBackgroundIBLProceduralSkyEnabled(bool(args["procedural_sky_enabled"]), True),
            "set World Background Dynamic Sky state",
        )
    _set_ibl_fields(edit, args, _BACKGROUND_DYNAMIC_FIELDS, "World Background")
    response.update(get_ibl_settings({"target": "background"}))
    return response


def set_ibl(args):
    """Load and edit IBL settings for World Lighting or World Background."""
    target = (args.get("target") or "lighting").lower()
    if target == "lighting":
        return _set_lighting_ibl(args)
    if target == "background":
        if "sync_sky_image" in args or "sync_sky_orientation" in args or "source" in args:
            raise ValueError("World Background uses background_mode; lighting-only options are not valid")
        return _set_background_ibl(args)
    raise ValueError("target must be lighting or background")


def key_ibl(args):
    target = (args.get("target") or "lighting").lower()
    if target not in ("lighting", "background"):
        raise ValueError("target must be lighting or background")
    rpy2, edit, query, unused_file = _rpy2_environment_interfaces()
    current_time = query.CurrentTime()
    method_name = "CreateBackgroundIBLClip" if target == "background" else "CreateIBLClip"
    _require_native_result(getattr(edit, method_name)(current_time), "create {0} IBL key".format(target))
    clip_count = query.GetBackgroundIBLClipCount() if target == "background" else query.GetIBLClipCount()
    to_int = getattr(current_time, "ToInt", None)
    return {
        "status": "ok",
        "target": target,
        "time": int(to_int()) if callable(to_int) else str(current_time),
        "clip_count": int(clip_count),
    }


def set_render_system(args):
    _ensure_no_project_load()
    if _render_system_transition_is_active():
        raise RuntimeError("A render-system transition is already running")
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
    active = job["state"] in ("queued", "waiting_for_dialog", "switching")
    result["dialogs"] = _transition_dialogs() if active else []
    result["cancellable"] = job["state"] in ("queued", "waiting_for_dialog")
    if result["dialogs"]:
        result["state"] = "waiting_for_dialog"
        result["phase"] = "waiting_for_dialog"
    return result


def _render_system_transition_is_active():
    return any(job["state"] in ("queued", "waiting_for_dialog", "switching") for job in _TRANSITION_JOBS.values())


def _ensure_no_project_load():
    from iclone_mcp_tool_project import _project_load_is_active

    if _project_load_is_active():
        raise RuntimeError("A project load is already running")


def _transition_dialogs():
    try:
        from iclone_mcp_tool_diagnostics import get_modal_dialogs

        return [dialog for dialog in get_modal_dialogs({}).get("dialogs", [])
                if dialog.get("modal", True)]
    except Exception:
        return []


def _run_render_system_transition(job_id):
    job = _TRANSITION_JOBS.get(job_id)
    if job is None or job["state"] not in ("queued", "waiting_for_dialog"):
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
        except Exception as error:
            job["state"] = "failed"
            job["phase"] = "failed"
            job["error"] = str(error)
            job["elapsed_ms"] = int((time.monotonic() - job["started_at"]) * 1000)
            return

    job["state"] = "switching"
    job["phase"] = "switching"
    job["cancellable"] = False
    try:
        result = RLPy.RGlobal.SwitchRenderSystem(job["requested_system_value"])
        if result != RLPy.RStatus.Success:
            raise RuntimeError("iClone could not switch render system")
        job["current_system"] = _render_system_name(RLPy.RGlobal.GetRenderSystem())
        _restart_mcp_listener()
        # Cancelling the conversion dialog may return Success without switching.
        job["completion"] = job["current_system"] == job["requested_system"]
        job["state"] = "completed" if job["completion"] else "cancelled"
        job["phase"] = job["state"]
    except Exception as error:
        job["phase"] = "failed"
        job["state"] = "failed"
        job["completion"] = False
        job["error"] = str(error)
    job["elapsed_ms"] = int((time.monotonic() - job["started_at"]) * 1000)


def start_render_system_transition(args):
    _ensure_no_project_load()
    system = str(args.get("system", "")).lower()
    constants = {
        "dx11": getattr(RLPy, "ERenderSystem_DX11", None),
        "dx12": getattr(RLPy, "ERenderSystem_DX12", None),
    }
    if system not in constants or constants[system] is None:
        raise ValueError("system must be 'dx11' or 'dx12'")
    if _render_system_transition_is_active():
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
    except Exception:
        del _TRANSITION_JOBS[job["job_id"]]
        raise
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
        job["elapsed_ms"] = int((time.monotonic() - job["started_at"]) * 1000)
    elif job["state"] == "switching":
        raise RuntimeError("Switching has started; use get_ui/invoke_ui to handle a blocking dialog")
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
    """Set output size, path-tracer options, or video codec and return readback."""
    results = {}
    if "width" in args or "height" in args:
        results["output_size"] = set_render_output_size(args)
    if "sample_count" in args or "value" in args:
        results["viewport_samples"] = set_viewport_samples(args)
    if any(name in args for name in (
        "preview_sample_count",
        "final_sample_count",
        "preview_denoiser_enabled",
        "final_render_denoiser_enabled",
        "video_codec",
    )):
        results["render_options"] = set_render_options(args)
    if not results:
        raise ValueError("Provide output size, sample count, denoiser state, or video_codec")
    return results


def _render_export_interface(required=True):
    render_module = getattr(RLPy2, "RenderExport", None) if RLPy2 is not None else None
    getter = getattr(render_module, "GetInterface", None)
    if not callable(getter):
        if required:
            raise RuntimeError("This iClone build does not expose the RLPy2 RenderExport API; rebuild and restart the application")
        return None
    interface = getter()
    if interface is None and required:
        raise RuntimeError("The iClone render-export interface is unavailable")
    return interface


def _render_export_options_snapshot(required=True):
    interface = _render_export_interface(required)
    if interface is None:
        return None
    methods = (
        "GetPreviewSampleCount",
        "GetFinalRenderSampleCount",
        "GetPreviewDenoiserEnabled",
        "GetFinalRenderDenoiserEnabled",
        "GetHevc10BitEnabled",
    )
    if any(not callable(getattr(interface, name, None)) for name in methods):
        if required:
            raise RuntimeError("The iClone render-export Python API is incomplete; rebuild and restart the application")
        return None
    return {
        "preview_sample_count": int(interface.GetPreviewSampleCount()),
        "final_sample_count": int(interface.GetFinalRenderSampleCount()),
        "preview_denoiser_enabled": bool(interface.GetPreviewDenoiserEnabled()),
        "final_render_denoiser_enabled": bool(interface.GetFinalRenderDenoiserEnabled()),
        "video_codec": "hevc_10bit" if interface.GetHevc10BitEnabled() else "h264",
    }


def _set_render_export_option(interface, setter_name, getter_name, value, label):
    setter = getattr(interface, setter_name, None)
    getter = getattr(interface, getter_name, None)
    if not callable(setter) or not callable(getter):
        raise RuntimeError("The iClone render-export Python API is incomplete; rebuild and restart the application")
    status = setter(value)
    if status is not None and not status:
        raise RuntimeError("iClone could not set {0}; check the active video export options".format(label))
    effective = getter()
    if effective != value:
        raise RuntimeError("iClone did not apply the requested {0}".format(label))
    return effective


def set_render_options(args):
    setters = {
        "preview_sample_count": ("SetPreviewSampleCount", "GetPreviewSampleCount"),
        "final_sample_count": ("SetFinalRenderSampleCount", "GetFinalRenderSampleCount"),
        "preview_denoiser_enabled": ("SetPreviewDenoiserEnabled", "GetPreviewDenoiserEnabled"),
        "final_render_denoiser_enabled": ("SetFinalRenderDenoiserEnabled", "GetFinalRenderDenoiserEnabled"),
    }
    values = {}
    for name, (setter_name, getter_name) in setters.items():
        if name not in args:
            continue
        value = args[name]
        if name == "preview_sample_count":
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10000:
                raise ValueError("{0} must be an integer from 1 to 10000".format(name))
        elif name == "final_sample_count":
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100000:
                raise ValueError("{0} must be an integer from 1 to 100000".format(name))
        elif not isinstance(value, bool):
            raise ValueError("{0} must be a boolean".format(name))
        values[name] = (setter_name, getter_name, value)

    codec = None
    if "video_codec" in args:
        codec = args["video_codec"]
        if not isinstance(codec, str) or codec.lower() not in ("h264", "hevc_10bit"):
            raise ValueError("video_codec must be h264 or hevc_10bit")
        codec = codec.lower()

    if not values and codec is None:
        raise ValueError("Provide at least one render option")

    interface = _render_export_interface()
    before = _render_export_options_snapshot()
    requested = {}
    if codec is not None:
        _set_render_export_option(
            interface,
            "SetHevc10BitEnabled",
            "GetHevc10BitEnabled",
            codec == "hevc_10bit",
            "video_codec",
        )
        requested["video_codec"] = codec

    for name, (setter_name, getter_name, value) in values.items():
        requested[name] = _set_render_export_option(interface, setter_name, getter_name, value, name)

    effective = _render_export_options_snapshot()
    return {
        "requested": requested,
        "effective": effective,
        "changed": before != effective,
    }


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


_HDR_WIDGETS = {
    "hdr_enabled": "qtHDREffectCheckBox",
    "method": "qtMethodComboBox",
    "brightness_threshold": "qtBrightnessThresholdComboDoubleSpinBox",
    "legacy_bloom_scale": "qtLegacyBloomScaleCombospinbox",
    "multi_scatter_intensity": "qtNewBloomIntensityComboDoubleSpinBox",
    "multi_scatter_size_scale": "qtNewBloomSizeScaleComboDoubleSpinBox",
    "kernel_type": "qtKernelTypeComboBox",
    "kernel_image": "qtKernelLabel",
    "kernel_scale": "qtKernelScaleComboDoubleSpinBox",
    "kernel_intensity": "qtKernelIntensityComboDoubleSpinBox",
    "scatter_dispersion": "qtKernelScatterComboDoubleSpinBox",
    "boost_min": "qtBoostMinComboDoubleSpinBox",
    "boost_max": "qtBoostMaxComboDoubleSpinBox",
    "boost_multiply": "qtBoostMulComboDoubleSpinBox",
    "show_input_value": "qtShowInputValueCheckBox",
    "composite_lerp": "qtCompositeLerpCombo",
    "glare_type": "qtGlareTypeComboBox",
    "glare_scale": "qtGlareScaleCombospinbox",
}
_OCIO_WIDGETS = {
    "profile": "qtPathtracerOcioViewTransformComboBox",
    "display_device": "qtPathtracerOcioDisplayDeviceComboBox",
    "look": "qtPathtracerOcioLookComboBox",
    "gamma": "qtPathtracerOcioGammaSpinBox",
    "white_point": "qtPathtracerOcioWhitePointSpinBox",
    "white_tint": "qtPathtracerOcioWhiteTintSpinBox",
}


def _visual_widgets(names):
    from iclone_mcp_tool_diagnostics import _all_widgets, _find_widget, _widget_summary

    widgets = _all_widgets()
    result = {}
    for name, object_name in names.items():
        try:
            result[name] = _widget_summary(_find_widget(widgets, object_name))
        except ValueError:
            continue
    return result


def _set_visual_widget(object_name, value, widgets=None):
    from PySide2 import QtGui, QtWidgets
    from iclone_mcp_tool_diagnostics import _all_widgets, _find_widget, _property_is_writable, _widget_summary

    widget = _find_widget(widgets if widgets is not None else _all_widgets(), object_name)
    if not widget.isEnabled():
        raise RuntimeError("Qt widget '{0}' is disabled".format(object_name))
    class_name = str(widget.metaObject().className())
    if class_name == "QColorButton":
        if not isinstance(value, dict):
            raise ValueError("color values must be RGB or RGBA objects")
        channels = [value.get(key) for key in ("r", "g", "b")]
        alpha = value.get("a", 1.0)
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1 for v in channels + [alpha]):
            raise ValueError("color channels must be numbers between 0 and 1")
        color = QtGui.QColor.fromRgbF(float(channels[0]), float(channels[1]), float(channels[2]), float(alpha))
        if widget.setProperty("Color", color) is False:
            raise ValueError("Qt widget '{0}' rejected the color".format(object_name))
    elif isinstance(widget, QtWidgets.QComboBox):
        index = widget.findText(str(value))
        if index < 0 and isinstance(value, str):
            matches = [i for i in range(widget.count()) if str(widget.itemText(i)).endswith(value)]
            index = matches[0] if len(matches) == 1 else -1
        if index < 0:
            raise ValueError("value is not an item in '{0}'".format(object_name))
        widget.setCurrentIndex(index)
    elif isinstance(widget, QtWidgets.QAbstractButton) and widget.isCheckable():
        if not isinstance(value, bool):
            raise ValueError("'{0}' must be a boolean".format(object_name))
        widget.setChecked(value)
    elif callable(getattr(widget, "setValue", None)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError("'{0}' must be a finite number".format(object_name))
        widget.setValue(value)
    elif _property_is_writable(widget, "value"):
        if widget.setProperty("value", value) is False:
            raise ValueError("Qt widget '{0}' rejected the value".format(object_name))
    else:
        raise ValueError("Qt widget '{0}' does not support value changes".format(object_name))
    QtWidgets.QApplication.processEvents()
    return _widget_summary(widget)


def _hdr_snapshot():
    from iclone_mcp_tool_diagnostics import _all_widgets, _find_widget, _widget_summary

    widgets = _all_widgets()
    controls = {}
    for key, object_name in _HDR_WIDGETS.items():
        try:
            controls[key] = _widget_summary(_find_widget(widgets, object_name))
        except ValueError:
            continue
    layers = []
    for index in range(1, 7):
        layer = {}
        for key, suffix in (("size", "SizeComboDoubleSpinBox"), ("color", "ColorButton")):
            try:
                layer[key] = _widget_summary(_find_widget(widgets, "qtLayer{0}{1}".format(index, suffix)))
            except ValueError:
                pass
        layers.append(layer)
    return {"controls": controls, "layers": layers}


def hdr_effect(args):
    action = (args.get("action") or "get").lower()
    if action == "get":
        return _hdr_snapshot()
    if action == "set":
        settings = args.get("settings")
        if not isinstance(settings, dict) or not settings:
            raise ValueError("settings must be a non-empty object")
        valid = set(_HDR_WIDGETS) - {"kernel_image"}
        if "layers" in settings:
            valid.add("layers")
        unknown = set(settings) - valid
        if unknown:
            raise ValueError("unsupported HDR setting(s): {0}".format(", ".join(sorted(unknown))))
        changed = {}
        order = [key for key in ("hdr_enabled", "method") if key in settings]
        order.extend(key for key in settings if key not in ("hdr_enabled", "method", "layers"))
        for key in order:
            changed[key] = _set_visual_widget(_HDR_WIDGETS[key], settings[key])
        if "layers" in settings:
            layers = settings["layers"]
            if not isinstance(layers, list) or not 1 <= len(layers) <= 6:
                raise ValueError("layers must contain between 1 and 6 layer objects")
            changed["layers"] = []
            for index, layer in enumerate(layers, 1):
                if not isinstance(layer, dict) or not layer or set(layer) - {"size", "color"}:
                    raise ValueError("each layer must contain size and/or color")
                readback = {}
                for key, suffix in (("size", "SizeComboDoubleSpinBox"), ("color", "ColorButton")):
                    if key in layer:
                        readback[key] = _set_visual_widget(
                            "qtLayer{0}{1}".format(index, suffix), layer[key]
                        )
                changed["layers"].append(readback)
        return {"requested": settings, "changed": changed, "state": _hdr_snapshot()}
    if action == "load_kernel_image":
        path = args.get("path")
        if not isinstance(path, str) or not path:
            raise ValueError("path must be a non-empty absolute EXR path")
        path = os.path.normpath(path)
        if not os.path.isabs(path) or not os.path.isfile(path) or os.path.splitext(path)[1].lower() != ".exr":
            raise ValueError("path must be an existing absolute .exr file")
        from PySide2 import QtCore, QtWidgets
        from iclone_mcp_tool_diagnostics import _all_widgets, _find_widget

        widgets = _all_widgets()
        hdr = _find_widget(widgets, _HDR_WIDGETS["hdr_enabled"])
        method = _find_widget(widgets, _HDR_WIDGETS["method"])
        if not hdr.isChecked() or str(method.currentText()) != "Kernel":
            raise RuntimeError("Enable HDR Effect and select Kernel before loading a kernel image")
        button = _find_widget(widgets, "qtLoadKernelToolButton")
        if not button.isEnabled():
            raise RuntimeError("The Kernel image loader is disabled")
        app = QtWidgets.QApplication.instance()
        app.setAttribute(QtCore.Qt.AA_DontUseNativeDialogs, True)
        pending_property = "iclone_mcp_pending_kernel_image_path"
        dialogs = [widget for widget in app.topLevelWidgets()
                   if isinstance(widget, QtWidgets.QFileDialog) and widget.isVisible()]
        if not dialogs:
            if app.property(pending_property) == path:
                state = _hdr_snapshot()
                remove_button = _find_widget(_all_widgets(), "qtRemoveKernelToolButton")
                if state["controls"]["kernel_type"]["value"]["text"] == "Custom" and remove_button.isEnabled():
                    app.setProperty(pending_property, "")
                    return {"loaded_path": path, "kernel_image_loaded": True, "state": state}
                return {"status": "loading", "path": path,
                        "next_action": "Call load_kernel_image again to confirm completion."}
            # The application picker uses Windows-native UI by default; keep this path inspectable by MCP.
            app.setProperty(pending_property, path)
            QtCore.QTimer.singleShot(0, button.click)
            return {"status": "dialog_opened", "path": path,
                    "next_action": "Call load_kernel_image again with the same path to select it."}
        dialog = dialogs[-1]
        file_name = dialog.findChild(QtWidgets.QLineEdit, "fileNameEdit")
        if file_name is None:
            raise RuntimeError("The open file dialog has no MCP-accessible filename field")
        file_name.setText(path)
        QtWidgets.QApplication.processEvents()
        open_button = next((widget for widget in dialog.findChildren(QtWidgets.QPushButton)
                            if widget.text().replace("&", "") == "Open" and widget.isEnabled()), None)
        if open_button is None:
            raise RuntimeError("The open file dialog did not accept the Kernel image path")
        open_button.click()
        QtWidgets.QApplication.processEvents()
        if dialog.isVisible():
            raise RuntimeError("iClone did not accept the selected Kernel image")
        app.setProperty(pending_property, path)
        return {"status": "load_submitted", "path": path,
                "next_action": "Call load_kernel_image again to confirm completion."}
    raise ValueError("action must be one of: get, set, load_kernel_image")


def ocio_profile(args):
    action = (args.get("action") or "get").lower()
    if action == "get":
        return {"controls": _visual_widgets(_OCIO_WIDGETS)}
    if action == "set":
        settings = {key: args[key] for key in _OCIO_WIDGETS if key in args}
        if not settings:
            raise ValueError("set requires profile, display_device, look, gamma, white_point, or white_tint")
        changed = {
            key: _set_visual_widget(_OCIO_WIDGETS[key], value)
            for key, value in settings.items()
        }
        return {"requested": settings, "changed": changed, "controls": _visual_widgets(_OCIO_WIDGETS)}
    raise ValueError("action must be one of: get, set")


def ibl(args):
    action = (args.get("action") or "get").lower()
    if action == "get":
        return get_ibl_settings(args)
    if action == "set":
        return set_ibl(args)
    if action == "key":
        return key_ibl(args)
    raise ValueError("action must be one of: get, set, key")


def register(registry):
    registry["hdr_effect"] = {
        "handler": hdr_effect,
        "main_thread": True,
        "description": "Get or set HDR, Bloom, Kernel, Glare, layer, and composite controls; load a custom EXR Kernel image by path.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["get", "set", "load_kernel_image"]},
                "path": {"type": "string"},
                "settings": {
                    "type": "object",
                    "properties": {
                        "hdr_enabled": {"type": "boolean"},
                        "method": {"type": "string"},
                        "brightness_threshold": {"type": "number"},
                        "legacy_bloom_scale": {"type": "number"},
                        "multi_scatter_intensity": {"type": "number"},
                        "multi_scatter_size_scale": {"type": "number"},
                        "kernel_type": {"type": "string"},
                        "kernel_scale": {"type": "number"},
                        "kernel_intensity": {"type": "number"},
                        "scatter_dispersion": {"type": "number"},
                        "boost_min": {"type": "number"},
                        "boost_max": {"type": "number"},
                        "boost_multiply": {"type": "number"},
                        "show_input_value": {"type": "boolean"},
                        "composite_lerp": {"type": "number"},
                        "glare_type": {"type": "string"},
                        "glare_scale": {"type": "number"},
                        "layers": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "size": {"type": "number"},
                                    "color": {"type": "object"},
                                },
                            },
                        },
                    },
                },
            },
            "required": ["action"],
        },
    }
    registry["ocio_profile"] = {
        "handler": ocio_profile,
        "main_thread": True,
        "description": "Get or set the RTX OCIO profile, display device, look, gamma, and white point.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["get", "set"]},
                "profile": {"type": "string"},
                "display_device": {"type": "string"},
                "look": {"type": "string"},
                "gamma": {"type": "number"},
                "white_point": {"type": "number"},
                "white_tint": {"type": "number"},
            },
            "required": ["action"],
        },
    }
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
        "description": "Get/set output size, preview/final path-tracer samples and denoisers, or H.264/HEVC 10-bit. HEVC 10-bit supports DX11/DX12 hardware-encoded MP4/MOV, panorama, and alpha-only output without supersampling; stereo is unsupported.",
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
                "preview_sample_count": {"type": "integer", "minimum": 1, "maximum": 10000},
                "final_sample_count": {"type": "integer", "minimum": 1, "maximum": 100000},
                "preview_denoiser_enabled": {"type": "boolean"},
                "final_render_denoiser_enabled": {"type": "boolean"},
                "video_codec": {"type": "string", "enum": ["h264", "hevc_10bit"]},
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
        "description": "Get or set World Lighting/World Background IBL state, or key the active IBL clip.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["get", "set", "key"]},
                "target": {"type": "string", "enum": ["lighting", "background"]},
                "source": {"type": "string", "enum": ["ambient", "ibl", "dynamic_sky"]},
                "background_mode": {"type": "string", "enum": ["sync_light_settings", "ibl", "dynamic_sky", "background_2d"]},
                "image_path": {"type": "string"},
                "enabled": {"type": "boolean"},
                "show_background": {"type": "boolean"},
                "light_source_enabled": {"type": "boolean"},
                "procedural_sky_enabled": {"type": "boolean"},
                "strength": {"type": "number"},
                "blur": {"type": "number"},
                "sync_sky_image": {"type": "boolean"},
                "sync_sky_orientation": {"type": "boolean"},
                "sky_brightness": {"type": "number"},
                "sun_brightness": {"type": "number"},
                "clouds_movement_speed": {"type": "number"},
                "time_of_day_movement_speed": {"type": "number"},
                "sun_time_of_day_offset": {"type": "number"},
                "sun_east_west_rotation": {"type": "number"},
                "sun_angular_diameter_deg": {"type": "number"},
                "cloud_density_offset": {"type": "number"},
                "cloud_transmittance": {"type": "number"},
                "horizon_height": {"type": "number"},
                "horizon_blur": {"type": "number"},
                "lower_hemisphere_brightness": {"type": "number"},
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
