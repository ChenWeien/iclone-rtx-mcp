import RLPy


_SEARCH_TYPE_NAMES = (
    "EObjectType_Prop",
    "EObjectType_Avatar",
    "EObjectType_Camera",
    "EObjectType_Particle",
    "EObjectType_Light",
    "EObjectType_SpotLight",
    "EObjectType_PointLight",
    "EObjectType_DirectionalLight",
    "EObjectType_Path",
    "EObjectType_LensFlare",
)
_SEARCH_TYPES = tuple(
    getattr(RLPy, name)
    for name in _SEARCH_TYPE_NAMES
    if hasattr(RLPy, name)
)


class _SearchTypes(object):
    def __iter__(self):
        return iter(
            getattr(RLPy, name)
            for name in _SEARCH_TYPE_NAMES
            if hasattr(RLPy, name)
        )


_SEARCH_TYPES = _SearchTypes()

def find_by_name(name):
    # The active Preview Camera is not always returned by FindObject, even
    # though it is a valid camera with a transform control.
    get_current_camera = getattr(RLPy.RScene, "GetCurrentCamera", None)
    current_camera = get_current_camera() if get_current_camera is not None else None
    if current_camera is not None and current_camera.GetName() == name:
        return current_camera
    find_object = getattr(RLPy.RScene, "FindObject", None)
    if find_object is None:
        raise ValueError("Object not found: %s" % name)
    object_types = [getattr(RLPy, name) for name in _SEARCH_TYPE_NAMES if hasattr(RLPy, name)]
    for object_type in object_types:
        obj = find_object(object_type, name)
        if obj is not None:
            return obj
    raise ValueError("Object not found: %s" % name)
