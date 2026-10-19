import os
import sys
import types


PLUGIN_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, "plugin")
)
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

sys.modules.setdefault("RLPy", types.ModuleType("RLPy"))

import iclone_mcp_tool_content as content
import iclone_mcp_tool_fileio as fileio


class _Search:
    def __init__(self):
        self.context = None
        self.query = None
        self.page = None

    def SetSearchContext(self, mode, main_tab, sub_tab):
        self.context = (mode, main_tab, sub_tab)

    def ExecuteSearchByText(self, value):
        self.query = ("text", value)

    def ExecuteSearchByImage(self, value):
        self.query = ("image", value)

    def WaitForSearchFinish(self, unused_timeout):
        return True

    def SetSearchPage(self, value):
        self.page = value

    def GetSearchPaginationInfo(self):
        return types.SimpleNamespace(page=1, page_size=25, total=1, page_count=1)

    def GetSearchResultCount(self):
        return 1

    def GetSearchResultSnapshot(self):
        return [{
            "content_id": "CID-1",
            "display_name": "Tree",
            "thumbnail_url": "https://example.invalid/tree.png",
            "is_pack": False,
            "is_installed": True,
            "is_purchased": True,
            "is_content_triable": False,
            "is_expired": False,
            "is_item_of_pack_triable": False,
            "metadata_prepared": True,
            "index": 0,
        }]


class _ContentManager:
    def __init__(self, path=""):
        self.path = path
        self.installs = []

    def QueryFilePathByContentID(self, ids, paths):
        if self.path:
            paths["CID-1"] = self.path

    def InstallContent(self, content_id):
        self.installs.append(content_id)
        return True


def _rlpy2(search=None, manager=None):
    search = search or _Search()
    manager = manager or _ContentManager()

    class _Ids(list):
        def Add(self, value):
            self.append(value)

    class _Paths(dict):
        pass

    return types.SimpleNamespace(
        EContentManagerSearchMode=types.SimpleNamespace(Smart="smart", General="general"),
        EContentManagerSearchMainTab=types.SimpleNamespace(Marketplace="marketplace", AIStudio="ai_studio"),
        EContentManagerSearchSubTab=types.SimpleNamespace(Item="item", Pack="pack", PackItems="pack_items"),
        ContentManagerSearch=types.SimpleNamespace(GetInterface=lambda: search),
        ContentManager=types.SimpleNamespace(GetInterface=lambda: manager),
        RArrayListWString=_Ids,
        RMapWStr2WStr=_Paths,
    )


def test_smart_search_returns_normalized_results_and_pagination():
    search = _Search()
    original_rlpy = content.RLPy
    original_rlpy2 = content.RLPy2
    content.RLPy = types.SimpleNamespace(RApplication=types.SimpleNamespace())
    content.RLPy2 = _rlpy2(search=search)
    try:
        result = content.search_content({"search_text": "tree", "page": 1})
    finally:
        content.RLPy = original_rlpy
        content.RLPy2 = original_rlpy2

    assert search.context == ("smart", "ai_studio", "item")
    assert search.query == ("text", "tree")
    assert search.page == 1
    assert result["completed"] is True
    assert result["pagination"]["total"] == 1
    assert result["results"][0]["content_id"] == "CID-1"


def test_load_file_resolves_content_id_and_reports_imported_object(tmp_path):
    asset = tmp_path / "tree.iProp"
    asset.write_bytes(b"asset")
    loaded = types.SimpleNamespace(GetID=lambda: "object-1", GetName=lambda: "Tree")
    objects = []
    manager = _ContentManager(str(asset))

    class _FileIO:
        @staticmethod
        def LoadFile(path, record_step):
            assert path == os.path.normpath(str(asset))
            assert record_step is True
            objects.append(loaded)
            return "success"

    original_rlpy = content.RLPy
    original_rlpy2 = content.RLPy2
    content.RLPy = types.SimpleNamespace(
        RStatus=types.SimpleNamespace(Success="success"),
        ELoadFileOption__None=0,
        EObjectType_Object=1,
        RScene=types.SimpleNamespace(FindObjects=lambda unused_type: list(objects)),
        RFileIO=_FileIO,
    )
    content.RLPy2 = _rlpy2(manager=manager)
    try:
        result = content.load_file({"content_id": "CID-1"})
    finally:
        content.RLPy = original_rlpy
        content.RLPy2 = original_rlpy2

    assert result["status"] == "ok"
    assert result["loaded"] is True
    assert result["content_id"] == "CID-1"
    assert result["imported_objects"] == [{"id": "object-1", "name": "Tree"}]


def test_load_file_reports_imported_lens_flare(tmp_path):
    asset = tmp_path / "Sunlight.iLflare"
    asset.write_bytes(b"asset")
    loaded = types.SimpleNamespace(GetID=lambda: "flare-1", GetName=lambda: "Sunlight")
    objects = []

    class _FileIO:
        @staticmethod
        def LoadFile(path, record_step):
            assert path == os.path.normpath(str(asset))
            assert record_step is True
            objects.append(loaded)
            return "success"

    original_rlpy = content.RLPy
    content.RLPy = types.SimpleNamespace(
        RStatus=types.SimpleNamespace(Success="success"),
        ELoadFileOption__None=0,
        EObjectType_Object=1,
        EObjectType_LensFlare=1 << 17,
        RScene=types.SimpleNamespace(FindObjects=lambda unused_type: list(objects)),
        RFileIO=_FileIO,
    )
    try:
        result = content.load_file({"path": str(asset)})
    finally:
        content.RLPy = original_rlpy

    assert result["imported_objects"] == [{"id": "flare-1", "name": "Sunlight"}]


def test_load_file_returns_install_started_when_auto_install_is_async():
    manager = _ContentManager()
    original_rlpy = content.RLPy
    original_rlpy2 = content.RLPy2
    content.RLPy = types.SimpleNamespace(RApplication=types.SimpleNamespace())
    content.RLPy2 = _rlpy2(manager=manager)
    try:
        result = content.load_file({
            "content_id": "CID-1",
            "install_if_missing": True,
            "confirm": "INSTALL_CONTENT",
        })
    finally:
        content.RLPy = original_rlpy
        content.RLPy2 = original_rlpy2

    assert result == {"status": "install_started", "loaded": False, "content_id": "CID-1"}
    assert manager.installs == ["CID-1"]


def test_load_fbx_maps_public_import_option(tmp_path):
    source = tmp_path / "asset.fbx"
    source.write_bytes(b"fbx")
    calls = []

    class _FileIO:
        @staticmethod
        def LoadFbxFile(*args):
            calls.append(args)
            return "success"

    original_rlpy = fileio.RLPy
    fileio.RLPy = types.SimpleNamespace(
        EImportFbxOption_Prop=3,
        EImportFbxOption__None=0,
        ELoadFileOption__None=0,
        RStatus=types.SimpleNamespace(Success="success"),
        RFileIO=_FileIO,
    )
    try:
        result = fileio.load_fbx_file({"path": str(source), "import_option": "prop"})
    finally:
        fileio.RLPy = original_rlpy

    assert result == {"status": "ok", "path": os.path.normpath(str(source))}
    assert calls[0][1] == 3
