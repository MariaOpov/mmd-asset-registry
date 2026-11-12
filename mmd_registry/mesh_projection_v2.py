"""CP23 B4 V2 new identity: bounded, static read-only PMX mesh projection.

The *existing* Registry mmd_registry.pmx.reader.load_pmx is the only PMX parser.
No PMX writer, network fetch, texture read, animation or geometry mutation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

PIN = '35b3a30962465a759c15fcd9780e8c47022b1928'
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_VERTICES = 100_000
MAX_TRIANGLES = 150_000
MAX_PAYLOAD_BYTES = 11_000_000


class PreviewGateError(ValueError):
    pass


def hash_source(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(chunk)
    return sha.hexdigest()


def validate_source(path: Path) -> Path:
    if type(path) is not Path:
        path = Path(path)
    if not path.is_absolute() or path.suffix.casefold() != '.pmx':
        raise PreviewGateError('A local absolute .pmx path is required.')
    path = path.resolve(strict=True)
    if not path.is_file():
        raise PreviewGateError('Source is not a file.')
    size = path.stat().st_size
    if size <= 0 or size > MAX_SOURCE_BYTES:
        raise PreviewGateError('Model is outside the bounded 32 MiB preview input limit.')
    return path


# Core is frozen to v0.9.5.12; Studio additions may reside in the same
# committed Git worktree. Never treat a new HEAD alone as a Core change.
STUDIO_LANE_PREFIXES = ('gui_a0/', 'creator_p0/', 'mc_a0/')


def _git_checked(repo: Path, *args: str) -> bytes:
    """Bounded local Git reads only, with no network or repository mutations."""
    run = subprocess.run(
        ['git', '-C', str(repo), *args], capture_output=True,
        timeout=15, check=False,
    )
    if run.returncode:
        raise PreviewGateError('Local Core identity check failed: ' + args[0])
    return run.stdout


def verify_core(repo: Path) -> None:
    """Isolated CP19 Core identity plus independent canonical source identity.

    Historical PIN -> CP19 direct parent is proved only in the exact bare
    store. Historical ancestry of canonical HEAD is NOT asserted. Canonical
    cleanliness covers the pinned119 paths only; whole-repo cleanliness,
    hostile concurrent mutation and production acceptance are NOT attested.
    """
    import hashlib
    import os
    from pathlib import Path
    import re
    import stat
    import subprocess
    import threading
    import sys
    import types
    import marshal
    import struct
    import contextlib
    import ast
    import dataclasses
    _contract = {'canonical_root': 'D:\\MMD\\mmd-asset-registry', 'cp19_bare': 'D:\\Assets\\MMDRegistry\\Studio\\Baselines\\CP19_R0C_9747_4291_12665_8308_BARE.git', 'source_root': 'D:\\MMD\\mmd-asset-registry', 'core_pins': {'mmd_registry/__init__.py': '91015f768b78bdb15a55da2df70ed8d5960e71c848a6dc8c005011c2b024d5c1', 'mmd_registry/_smart_part_confidence.py': '643d37ac9e74a210f14bebf8441213d7324494b4a806e778c3ccbdbfcb08e64d', 'mmd_registry/binary_reader.py': '241d2f9efc6059ee5b5bbc5808bf1ecb2a8c2c08e2d1bf917fb72017c2325521', 'mmd_registry/bone_cli.py': '65cfb5a1e4ef2c7a99d98e4d87ac2d10219aed5a0911cfd6aba5970c60cfc675', 'mmd_registry/bone_details.py': '1bfe45da83645eda7fa159f2e82560c434ea2c39d086103fd0386f6468f06d01', 'mmd_registry/bone_explorer.py': '22a2130e11a5341b40937fab96e5c99f63993ce0083b342f6c9b666bb82d698a', 'mmd_registry/bone_hierarchy.py': '0222298459d16020fe3c286cf463d9ca4c210f58c80a8af185ab369c9df8aa5d', 'mmd_registry/bone_names.py': '5003735aa7b8896fb5f00de76bd0687b2c480c364cbf36f3290c27f8e596c806', 'mmd_registry/bone_search.py': '2d814e48372bf41d65cd67a67d2b5ce6300a69214ab4e28c256812dd2c33a103', 'mmd_registry/bone_semantic_inference.py': 'c35e93400b54ac66731ac82114c1a19d9bb30244ae04aceed0fb4ea25a62d379', 'mmd_registry/bone_semantic_resolver.py': 'b72c482a80a9f7fdf6ea31e6cbd91a8ab4da0166b9188b0174b99ccc127c338a', 'mmd_registry/bone_semantics.py': 'd5aaf1fa7c1bb0396a47191d4e267d0c28a115508e598bea01527662711fc94b', 'mmd_registry/capabilities.py': '97a09b17a324a13d30a0956a794e2ef73d0e2c0dd8975bb315abe476ab40f9de', 'mmd_registry/cli.py': '26213f86095d48a7bd4c5399591f220e7b9432d53eb0014771cf09e345a3575d', 'mmd_registry/constants.py': '79ca95ac8184866d9502314aae8fcd17a6e543e4c4a0a95683ddf7a3d7bdf0c9', 'mmd_registry/dependency_diagnostics.py': '9d4c4dc1a5ecdc27448f551da4a330266d85dd41fa330de8f91def2694d57945', 'mmd_registry/diagnostics.py': '2e1fe85f448908e711237e4586ff46ac10d3cf69fdd089aa94f582526de5e439', 'mmd_registry/hashing.py': '3b2820fe06fad330c697c7d27824b665a9321bdf80a3698fcb8c9e44fbdc4e87', 'mmd_registry/model_inspection.py': '78d8bb91b2ac3be1d24686f030bd0cea34c0bfd69c483e4b8352de413a0a54cf', 'mmd_registry/model_scanning.py': 'c65ea9ed6a50b820b2a2ee88c7f2d2289496230b042edf6e75d50c6654cc3b77', 'mmd_registry/pmx/__init__.py': '0a061ea0b7abaaf42dba6c98b8ab23a76cfb5f7b8a089a3d79c82cd47105cbfa', 'mmd_registry/pmx/bone_reference_remap.py': '19e678489bc57733cd5279bab2d6b8ffade873cad488c2eafa3689d7593b9c2d', 'mmd_registry/pmx/collection_transform.py': 'fbbf477e930a6b0ca57210b70436f1e299819db232b48d52e1b6544841cd6f07', 'mmd_registry/pmx/document.py': '9d058348420d09d4e51e272e3e771ab6b80ef2e13f2d2ac783bf59bbf6d965a8', 'mmd_registry/pmx/editing/__init__.py': '9e53bc2ec273808eed23b5044e5fd859b5251fc87609b5b6273644f2d66fe5b4', 'mmd_registry/pmx/editing/audit.py': '0efaf341f86d6aa9cb5d7d4f0802fc7f3d6caf467bdc9be33c94eadb8f92fca6', 'mmd_registry/pmx/editing/catalog.py': 'a9aca1ee62cfd9079267e2efb80953a8c63502dbd53f2141443e027e34753355', 'mmd_registry/pmx/editing/diagnostics.py': '9d901fe114b7629795aa9c71aa0542eb6b9fc095cc8ea29b22fd4b74143a82a1', 'mmd_registry/pmx/editing/engine.py': '2effb5dccb73b03bca76f93cc954c0be1a059c24d360594498488da23651fd2c', 'mmd_registry/pmx/editing/errors.py': 'afed2fdb8a6be80b147f79499acab6a69e20f9264165cc3188e66742e8db5ddb', 'mmd_registry/pmx/editing/explain.py': 'b19821588bf1d6a04c20245c7597ab33067f5d875054804ea8c01f6981b6e326', 'mmd_registry/pmx/editing/json_loader.py': 'd0a56ccd468989a9a6d1ce5c9cb3d7290cac011579bf848bd4194a57108f7d72', 'mmd_registry/pmx/editing/numeric.py': '6e16115f0c32051f294419c02d2258bbeb5134343bf54f4e11022abce21d65d5', 'mmd_registry/pmx/editing/operations.py': '20e0ef68570ecd684822098517415c8630a8e3b4680d7021b05cef4e87cd5b14', 'mmd_registry/pmx/editing/output.py': 'a08bb80302f9cf24bfce19e6a0cccd6f0e7859a10156bbfc20b93771c623957e', 'mmd_registry/pmx/editing/path_policy.py': '541488d2d1448b204fca7856522528a64cf3e854d1e2e9d4c349cac0652f0990', 'mmd_registry/pmx/editing/plan.py': 'af5694b359b7b2adf3b29e46492491c9f912be8d131f913f473dcd39d4442643', 'mmd_registry/pmx/editing/preview.py': 'e0aab691c4cc3a16bce9a20e5c7e65926fa6f0af9896835d1ad3ad443869f87d', 'mmd_registry/pmx/editing/template.py': 'fdc630173b6baf8aa0461622096b9adaffb432e94c41d085a943a5d6f283f791', 'mmd_registry/pmx/editing/validation.py': 'ab65a4e956adee490469dc30a748fd92bf762df9f64ccb0919d5925b56ea7d18', 'mmd_registry/pmx/errors.py': 'ca387c6b7ff2b2c57a9cb640d6755679428d92687df667efd17789ab6d50178c', 'mmd_registry/pmx/geometry_material_remap.py': '004b0e10aae7b9829e378bd71de4b0612f0e74debf2d4feaa2ce80a8e70ffcab', 'mmd_registry/pmx/index_remap.py': '3eff15dadac04be6536e1363f7add309d7d4303b307bfde42d11be113b71c5f8', 'mmd_registry/pmx/morph_display_remap.py': '704c8c898f12602874b1839a69b5b06bf0d4ff0f2ff4ddb394067ad6be823a13', 'mmd_registry/pmx/physics_reference_remap.py': 'c3a98990b54818f8e79a3907c2046b790d9a73a4d90fb263e86530cc07725ce8', 'mmd_registry/pmx/reader.py': '9002d1a1662624a294a7a6d1ce2b8e446e915527479a21ba3b429e4fb731e16d', 'mmd_registry/pmx/reference_diagnostics.py': 'b59a65d25ca0e40e25bafb6c2f56224699f2e54fa992d62ae9e0cb41fd168bad', 'mmd_registry/pmx/reference_graph.py': '4595ab9670e20970ffdf281d4b8758a1ec03c76c5c9ac2c2e9bea2b763c438fa', 'mmd_registry/pmx/reference_model.py': 'c7fddb2af2ac6b0eda0ed2ac718168d0559c46dae6b8052487228101a195c839', 'mmd_registry/pmx/reference_queries.py': 'c5c7029bd6a9a9ea69c73c051417007f6e5aeb7c790e6ff883d4d6c208244696', 'mmd_registry/pmx/roundtrip.py': '5d17e6630a816021bcbe6975c0331cd94999fad2fbac363c820a06747ec14540', 'mmd_registry/pmx/sections/__init__.py': '17942ee99898d61d547c1a5d54ffac4d5016f2f17a0603b8cb1d28df1e23ad79', 'mmd_registry/pmx/sections/bones.py': '21d5359fae24a1ca613a91f862b605f66f4b029da8b900639d1e2d8153af24b7', 'mmd_registry/pmx/sections/display_frames.py': '697d7ef76a16610e89d2f93a2a4d09459d718803d8433b1fdda8ca5bc1d28852', 'mmd_registry/pmx/sections/geometry.py': '7581dbf1ea07836344b74a1f1fde3d78b3046e886a9096b4af475b0d5ff6c43b', 'mmd_registry/pmx/sections/header.py': 'f3bb8ad9bc61fa04912368eec882cbbf81f4f0f50c96a5a5f01e6b63cd1c0475', 'mmd_registry/pmx/sections/joints.py': '4e772cead842ee799463128b3c141ad37ee89e6eda8e5c99e47076a3f33caab1', 'mmd_registry/pmx/sections/materials.py': '6359526db97a74ed81d2a8b8cc74c7614ec34008cafcaa60fc2327b66234279a', 'mmd_registry/pmx/sections/morphs.py': '56254fb2a5f08462bffb6c850645e42b2d74323487d3bb2b0494e45c9732e2d2', 'mmd_registry/pmx/sections/rigid_bodies.py': '7fccec71965240949fd87f8af5a38c72ac90d6c3c354bad1d317284f15800f3c', 'mmd_registry/pmx/sections/soft_bodies.py': '84ee7985d82a04d8837d8bfb9be9ef47cb44558b51931b6639e1e4fd181572f1', 'mmd_registry/pmx/sections/textures.py': '64d8b242a55b044911c247d4600d99e6b603d94a7df755772eb8f6196fea19c7', 'mmd_registry/pmx/structural_bone_insertion.py': '0b0ab00f323a7f0349bb72420d59cb9b584183640003ed7b6896bad797482911', 'mmd_registry/pmx/structural_capacity.py': '0fe523f9d83093a93e325dafa2e0daadd63d570730adccab4f7a320c9c2bbbb6', 'mmd_registry/pmx/structural_coordinated_insertion.py': '9e4c37b97fc0485c1f1b4f965dc2aaa15fdaadef0557a3f314e0e15281deab99', 'mmd_registry/pmx/structural_insert_intent.py': '14de0ba04d633baa92f2ce214f87b56a30cb7e4ed5dba0b9cfc4be985c968bff', 'mmd_registry/pmx/structural_invariants.py': '66d6129c89b42d60406b1e0febd11da4363afeeb743b8078c758be6e20fadc66', 'mmd_registry/pmx/structural_material_insertion.py': '3bf4a17b095225ef9b3ad352dd85e38d4278116eaed1b878fd3a3c87bd1f7337', 'mmd_registry/pmx/structural_morph_insertion.py': '152ce3acc743665abd726dab827a03dd19b46e309305205db06f2c2896c707df', 'mmd_registry/pmx/structural_orchestrator.py': '44f7a00c0a49c4275652748b4fa497fbf584fe9319ad6e0b2ebd0988ecfefe1b', 'mmd_registry/pmx/structural_output.py': '846dd5bdf184d557b5dba632a9e4fe8ad16e0c1d5eae3a5bafecb49b589f5732', 'mmd_registry/pmx/structural_preview.py': '9b30c8d8fa6b4f9f2715b7e86aafd5054b7eaa75ee2153bd520a9fc818524a82', 'mmd_registry/pmx/structural_reference_shift.py': '6ba3d97a32866dfbf7e0c9e48be97f65a96176b2cb60e37ecb0aa714c70e8dd9', 'mmd_registry/pmx/structural_rigid_body_insertion.py': '11224f9200ba538dc5a72a46cc24b6bdf0cef369a2010a940c876a774ceae9d1', 'mmd_registry/pmx/structural_texture_insertion.py': '6f3de4ba09f17bbf53dc65c5ff99a1da4261409b68b9e9f8fb6b4e851a6048e2', 'mmd_registry/pmx/structural_transaction_composition.py': '918d2c1f56c5534af400fc637832527fa3583b59c9d13013d13df1bd027905c8', 'mmd_registry/pmx/structural_transaction_dependency.py': '28fdfdd1cb7b356a432f37afd2d41a9ed1ec6254ba8597b8b918a99333245d56', 'mmd_registry/pmx/structural_transaction_insertion.py': 'ab9520623ce556cb9b0017b490b134153dcc4ce4e834035a42073ff10c58c24f', 'mmd_registry/pmx/structural_transaction_placement.py': 'f40dcdb55f978ef7e5aed77a915bc24a7a8d50320068a94330a6e2b8fe2f2a7d', 'mmd_registry/pmx/structural_transaction_preflight.py': '402dcb41e2621dd5a7805c6f29ef1f57ff1f7211396169bbaf75e2d8addcf0e4', 'mmd_registry/pmx/structural_transaction_preview.py': '7b9052c5f59d7debc56fade817a78ccc96fc77873043b5a7e96344c623621e67', 'mmd_registry/pmx/structural_transaction_reference.py': '63d50f651e9a0b535b6a50d5ecf33c9db40ffee8670b2e6c1817f5770c2524cd', 'mmd_registry/pmx/structural_vertex_insertion.py': '6ba2d47695b9315be4781bbcfdc5ec9e386e6e28bc20fbe675b134ce2c5e3d9f', 'mmd_registry/pmx/transaction_plan.py': '4aa47dc4a0e7a5204ebfa1c7bb9bdaf896bdff181daa23e2a29246933ef9fc2d', 'mmd_registry/pmx/validation.py': '7079b5b98bba608768048846e78fe692176185857fd5199af183007bd2a6353c', 'mmd_registry/pmx/writer.py': 'f4def16ce504a18156ffe4c649ac3f8a54fc32967e9f8d89e0926f8b19c03c10', 'mmd_registry/reporting.py': '434ab0ba54b3ef39589e959f0f92b1cb77aab634006efbb215fe0d96876839fa', 'mmd_registry/rig_analysis.py': '0630a93950c9ce78515a12ba94ac87dc7472b52372a475d931245cb41c79a609', 'mmd_registry/rig_cli.py': '3ad508322f4cb87c6b9f38d9952e83e169f23156797cc9f0c5d4487002e12151', 'mmd_registry/rig_diagnostics.py': '0e9a980a5757484ee954376546216b01c302c99674111dc3ad8929752baad0f7', 'mmd_registry/services/__init__.py': 'd0db2a0c0c6b0d90d34025ca12bbf1f37f8e6d6c6a313a1a8f6f3413a1639d31', 'mmd_registry/services/_smart_inspection.py': 'cb30c7e68f9bdd366e9096ce0a57dd146a2921dcfec7d8cc8e83b22bacfbee00', 'mmd_registry/services/structural_authoring_builder.py': 'ab90b8d82f56a9a896629c706e0d56424c3d9ab77d3aff6e9ac6892356bb8a24', 'mmd_registry/services/structural_authoring_catalog.py': 'fff01b35346c2d5980417a88f015a30ef81aca6913ef9ffb13e0766d37680e16', 'mmd_registry/services/structural_authoring_diff.py': 'dc31eff579cea319e51d66aef541d9114f2a2b583b8394c47da186c9e4769184', 'mmd_registry/services/structural_authoring_formatter.py': '3a29bd7a636479e6fd1f35830056e5612dbca0a588ec09de58f88b9ab3fe2436', 'mmd_registry/services/structural_authoring_selector.py': 'c60e692ca81882a85fc67a8a9a24a3552707eb6eb987023822cf9189391160be', 'mmd_registry/services/structural_bone.py': '5fd1c5ef43176af9bd405b0fcb6e599c5a21b86d5eb07a9e58dbdd9bf2575f1d', 'mmd_registry/services/structural_material.py': 'd5393519092e908995b00969cbbc3a18f6fb8f7dcb491da0d5a6b26c97f8ac4d', 'mmd_registry/services/structural_morph.py': '1041933e118002464c96c6257ca5ae9e184862dfbbeb5ccddf2269846f26bf28', 'mmd_registry/services/structural_reference.py': '185432db537306d1cc1efbd490a866da780def671822842b13ebf507c8a90e6d', 'mmd_registry/services/structural_rigid_body.py': 'fb649bfdd996d80060de1dfcd3ef3cc5beec825c5bf3481a2306f0cb5ec35427', 'mmd_registry/services/structural_texture.py': 'ce571584b1427ace627bb737b1385b7d7686abb59baa718e81bab261e363235f', 'mmd_registry/services/structural_transaction.py': '19bf28990cb58c49faa4d88f7d6a393546b98584358cb211282a7c0fb8005501', 'mmd_registry/services/structural_transaction_plan.py': 'eab438c4fc8ab887a9d49d94d82aa0c3ec6ac70bfa1b40670d98c21ceb417f21', 'mmd_registry/services/structural_transaction_plan_apply.py': '8db4a07f6d5b07c91fb3c0be598606d80ca45fe92eda576526894f76ea82b1b2', 'mmd_registry/services/structural_transaction_plan_preview.py': '8f6c4db7c00838e08edc65a651c6a4be5b55f697f2548c18fa5227b06052d8b5', 'mmd_registry/services/structural_vertex.py': 'd9b2bc19ed1ed9a0a36d4c4aef8983c2178a7fc29ed333cb06226c61e40efded', 'mmd_registry/smart_cli.py': 'f7bc1a36f7acaecf96bb3f8bee72647bbbf24d47816ed66ee7183980f66fa1d8', 'mmd_registry/smart_part_confidence.py': '04068b8b7b3bf8fc09ecc2e9fff495a9957f942a1c0829f3b85e4109ea775a25', 'mmd_registry/smart_part_detection.py': '0f48844a91d7d528b34491c5f397408c0a82e12e5f6c154c2ed3d500821af043', 'mmd_registry/smart_part_explainability.py': '1dfe204b39aec1fefa8ad1e0098fdb32e18f3eaf8c86c7fcc384ea3708ffcbe0', 'mmd_registry/smart_parts.py': '9ee61c95536bf2083af88f7ccc181c569864ae0e63260b49e9ca302a698c9450', 'mmd_registry/texture_path_semantics.py': '5a9aaf5ce1c69f1c66f871364d064ec78d3e3ff1fe96c105f8a35de735560877', 'mmd_registry/texture_portability.py': '9d5fadb6317e8a25e91df6d18d590a28194f2121d9c1effc2d806853c2e392c2', 'mmd_registry/texture_portability_cli.py': 'cee6bdd325882c40f331a00bebbf3301cbd3004095d95c0c8b5537696580cccb', 'mmd_registry/texture_rewrite.py': 'd6d9ebfd071d9cdb7dc8f07ceb45813dd61ffbbd4636d783dc2137ced5085573', 'mmd_registry/transaction_plan_cli.py': '464dbe5472bbdefaf3ea81cb1b8605f7d47ee63cfbc5a4adcdb854e3280783b4', 'mmd_registry/validator.py': '834c42cc188277509fa0ea1b8cc1895f1b6d7c34a9d525b285f235b603854fdd'}, 'core_oids': {'mmd_registry/__init__.py': '0bf9cf004669791818db7427b81419ee7b0ba6ca', 'mmd_registry/_smart_part_confidence.py': '1016c83b249fa753ff846b501b32958ecc2a0cdb', 'mmd_registry/binary_reader.py': '8dc518ab4ce17d6973bad6ab4f873671c5db29db', 'mmd_registry/bone_cli.py': 'd42cd46730da6c993ade90c7913ae752a1b83d8e', 'mmd_registry/bone_details.py': 'd95ac6068c657a602b8502bce453db1b2caf5ad2', 'mmd_registry/bone_explorer.py': 'b2d2fcb69673cf1d093e09be6eff24a195d36746', 'mmd_registry/bone_hierarchy.py': '78229626f0d043602c193513e6a4cd525add2c43', 'mmd_registry/bone_names.py': '09ae55a38c335d9216ec7afbbe024a25e0131d17', 'mmd_registry/bone_search.py': '057bb77a823cec93a10aef7ab6bcf06c092b015f', 'mmd_registry/bone_semantic_inference.py': '05ba2d103774d143bd4d11be6d17711ceaf12749', 'mmd_registry/bone_semantic_resolver.py': 'cd98be10fe90e703947d1a0dd5787baa8797d605', 'mmd_registry/bone_semantics.py': '01520f172355a0e73dc781ab986d222e76b7816e', 'mmd_registry/capabilities.py': '36bfa2440e08754d7bcf35e31a0e58de2cb31ff7', 'mmd_registry/cli.py': 'f50d7d811432ef1599d2bd29c0e15787c45a1c5d', 'mmd_registry/constants.py': '2983c3e94ebeb47ae5239eb629bf5f8662d5dc18', 'mmd_registry/dependency_diagnostics.py': '16b915af3ec6c86c7f9d4f127b969ca5b5742600', 'mmd_registry/diagnostics.py': 'cb64a89b34260aad2c1e55a681936285ba990e7d', 'mmd_registry/hashing.py': '86d6448d6334ba0d22683c29660109fd3d83f3ea', 'mmd_registry/model_inspection.py': '9fb802a1021dfbd7289b1725dd7820d9386d7133', 'mmd_registry/model_scanning.py': 'd89d4d49c8494b359f45715699280d9cebd279f6', 'mmd_registry/pmx/__init__.py': 'f4710cae5c0c7cba4cdbc602019128ebc2928d60', 'mmd_registry/pmx/bone_reference_remap.py': '46f4107e3fdb1fb993c3d53c28ce7c9c5e80ba7a', 'mmd_registry/pmx/collection_transform.py': 'c2c7af7ccc62bca3c1bac18293f29db5d7c96471', 'mmd_registry/pmx/document.py': '91220c68fe790e7941d5f17817b315bb018c746b', 'mmd_registry/pmx/editing/__init__.py': 'c9f201695a5dd284e0662f7fd814c8be9c7fa407', 'mmd_registry/pmx/editing/audit.py': '175986b0bf68c51fbf5ef5ab9e6b8c01975119e7', 'mmd_registry/pmx/editing/catalog.py': 'ce6dadb5424476baa4bb317981241019223b78d4', 'mmd_registry/pmx/editing/diagnostics.py': '209b09185995f48dd654d3db6d5cf2085e84fee3', 'mmd_registry/pmx/editing/engine.py': 'feab452e49de38e89175425845ba21aecd019730', 'mmd_registry/pmx/editing/errors.py': '94ebd2443738d7ea31f901c5306fa64326d5e98b', 'mmd_registry/pmx/editing/explain.py': '95c655ff121912be8d7d84f5ba4d42244740b2b7', 'mmd_registry/pmx/editing/json_loader.py': '240667b0aa8afd488baea0215608a72048cd465a', 'mmd_registry/pmx/editing/numeric.py': 'f3aa1187bae5344d83fd97e60cc1070658ebd1e4', 'mmd_registry/pmx/editing/operations.py': '146a12724ca5b17c6bca329cf3b50f67500bf215', 'mmd_registry/pmx/editing/output.py': '69f7de6ae92e15b7115045a3b0f75f15162b6452', 'mmd_registry/pmx/editing/path_policy.py': 'fcffb5939bbcacf61ddb209b82d2298838d9bb0a', 'mmd_registry/pmx/editing/plan.py': '4063ab6897b82cf679afae8cfaf838ca3d7d1710', 'mmd_registry/pmx/editing/preview.py': 'd8770e9f16060508179de807a49a3dac06689a62', 'mmd_registry/pmx/editing/template.py': 'c7a61a0332733598670cd55364a3d28ccd7e138f', 'mmd_registry/pmx/editing/validation.py': '73cd4281814aaac7d0e3a59dff8e583dcd30aa15', 'mmd_registry/pmx/errors.py': '028f4379e45b6ec3b546a89cfc9870217bb2ecab', 'mmd_registry/pmx/geometry_material_remap.py': 'f148704dd7f38c33688ba48f8012623983f6aae3', 'mmd_registry/pmx/index_remap.py': '86c3e2b4982f908bfa54db29a94fdbf298448a5f', 'mmd_registry/pmx/morph_display_remap.py': 'b46dd624ec6b8206ec4a41414f3d1dcd42be0b09', 'mmd_registry/pmx/physics_reference_remap.py': '15c1653986fb4d77409a32da4e7a07e1c43ab8f6', 'mmd_registry/pmx/reader.py': 'c7e46de434bf50782f2da4db364ffb8b28ba053a', 'mmd_registry/pmx/reference_diagnostics.py': '6ca81fc8919768fcb60754537c21e6887fa6758d', 'mmd_registry/pmx/reference_graph.py': '1e8f14e85bdae931934b49b2ea648c888dc11ee6', 'mmd_registry/pmx/reference_model.py': 'd9993b627da319b55fc69b0bd2e9c19aea60f917', 'mmd_registry/pmx/reference_queries.py': '4e1fb1a9e080ec4dfb5cde2837f032e422bb063d', 'mmd_registry/pmx/roundtrip.py': '0be64cb617d2f3ab11f638ffd149a1478981745d', 'mmd_registry/pmx/sections/__init__.py': '16bcc96091508fbc11d7942261dc94e0b5663769', 'mmd_registry/pmx/sections/bones.py': '0031cac42ec89beeebea91b8457675d2fc9a7bbf', 'mmd_registry/pmx/sections/display_frames.py': '1b387eac87e9eee14cd365907c0c1f93c634f175', 'mmd_registry/pmx/sections/geometry.py': '04fa7aea001dbc2f870b463cbd61bd4f3360551c', 'mmd_registry/pmx/sections/header.py': 'fea855d99e92669a760212d3f9a0cae72cd4fb41', 'mmd_registry/pmx/sections/joints.py': '69011a8236536bed200e83a9048d1b8bc2c1987d', 'mmd_registry/pmx/sections/materials.py': '15873ba21881e852e5be23b417da0c647adf9890', 'mmd_registry/pmx/sections/morphs.py': '490f3832579b0e74eef98d061dfbe9290735b534', 'mmd_registry/pmx/sections/rigid_bodies.py': 'ea9d9b146d7bc318829d025b80fa54219dad55f1', 'mmd_registry/pmx/sections/soft_bodies.py': '00a226bf664c6b6b57907401cefc1a0a079f8fba', 'mmd_registry/pmx/sections/textures.py': '6ef7466c9f86965c6e715ef230267871abd7695b', 'mmd_registry/pmx/structural_bone_insertion.py': '7ae089110c507541930e9d0e622ad4fa4c3b7bf8', 'mmd_registry/pmx/structural_capacity.py': '31a958779d8e8246bc269b43cc2831e9746291d6', 'mmd_registry/pmx/structural_coordinated_insertion.py': 'd6d8c85cb8f41c997c44ce5c28e8d1078b0d3c47', 'mmd_registry/pmx/structural_insert_intent.py': 'f8fbde6a60eec41a415be3143a9e8f72044525fe', 'mmd_registry/pmx/structural_invariants.py': 'ec83fb132d8490ed791ecaf5f999ec57259a4559', 'mmd_registry/pmx/structural_material_insertion.py': '80ab2dc91aa26a107846036cee04cd1b451f654d', 'mmd_registry/pmx/structural_morph_insertion.py': '8454ffb102f4cc0ef4e28f96b14b3f3e4fd547b1', 'mmd_registry/pmx/structural_orchestrator.py': '507db4bc9e0f654d76ddb316130db380a3c56b61', 'mmd_registry/pmx/structural_output.py': 'fb42713e1aacd2550c49be8c5b2d4cb3de8687f1', 'mmd_registry/pmx/structural_preview.py': 'd52a422a28eb317d5bcf6c7d18a8a083b01d391a', 'mmd_registry/pmx/structural_reference_shift.py': 'e68383a44a40746c592a61710fa42a56961fda7d', 'mmd_registry/pmx/structural_rigid_body_insertion.py': '69e1ce7a1a0f8fe57a308e5e9ca5b89fca72c12f', 'mmd_registry/pmx/structural_texture_insertion.py': 'f1f49e32c6372b6ed2d65e96cea74d638ef030f3', 'mmd_registry/pmx/structural_transaction_composition.py': '1d6b45c94bb631ddc647c1e0ffe4ac9f738a378e', 'mmd_registry/pmx/structural_transaction_dependency.py': 'f14d90785b3056e36d64106db481443e7b52a45a', 'mmd_registry/pmx/structural_transaction_insertion.py': '6dbd662b8929500abaf07e01414056f1d5ad89be', 'mmd_registry/pmx/structural_transaction_placement.py': '80c83eaae75d482cf3d08d540f3e6b0386138008', 'mmd_registry/pmx/structural_transaction_preflight.py': 'ccdd526456f9872fbad6f98a52cf96d07ad803a6', 'mmd_registry/pmx/structural_transaction_preview.py': 'c6214e7d5492bb34741794a20b0174028b68ac52', 'mmd_registry/pmx/structural_transaction_reference.py': 'c1957a225ed28567cd940fd119d173ac9484d776', 'mmd_registry/pmx/structural_vertex_insertion.py': '5dfc62df5738b040f371a88c718b318a9a6d236d', 'mmd_registry/pmx/transaction_plan.py': '66406278260ef345d48059f7583105a6586b7371', 'mmd_registry/pmx/validation.py': '14b41cf9b74429dbe21c454f0994aff27924c99f', 'mmd_registry/pmx/writer.py': 'a3a6fa4252c24678b76d650810b47d6c5757f2b4', 'mmd_registry/reporting.py': '6ae94afeaee2c915fb748041c1bf6dbaae6f9692', 'mmd_registry/rig_analysis.py': '85ee022094dbb9d992516c471c7ba10c3ee50746', 'mmd_registry/rig_cli.py': '71a78921490457a351dbada1d217835ddbb46d0e', 'mmd_registry/rig_diagnostics.py': '8f4103e3b5b1c5186014e52b434df1d5ab0d455c', 'mmd_registry/services/__init__.py': '0d1dac3dd686c306950e947214f4062ecff11a7a', 'mmd_registry/services/_smart_inspection.py': '2f8453403940c4aa376b77d953c5d83ad3d8c77a', 'mmd_registry/services/structural_authoring_builder.py': '4e0ea7d2f4d575ee7db30b397eafdfaabec4485b', 'mmd_registry/services/structural_authoring_catalog.py': '43500b61cbce1f93096248c54d9901f3f3494026', 'mmd_registry/services/structural_authoring_diff.py': 'dbd551e054ffc93e4df336be356c28dbb500eda9', 'mmd_registry/services/structural_authoring_formatter.py': 'afd370a11bd133f0b588e018b9a5da1f9b56b80e', 'mmd_registry/services/structural_authoring_selector.py': '5b5b51baf9e09bd104982ddbfde575212c1d87e2', 'mmd_registry/services/structural_bone.py': '8020bb9b4572ad4cd451e0e91c24d9de0fd42b63', 'mmd_registry/services/structural_material.py': '8e4c11ef7e2a04423894edf3e7f59736f33829ea', 'mmd_registry/services/structural_morph.py': '545af9e805d0ad66b86471464cec2a1b9fd4d9a4', 'mmd_registry/services/structural_reference.py': '95f82596aff67845965c592babdd37acf9d352ee', 'mmd_registry/services/structural_rigid_body.py': '23859c40c58224c646c3634040b87f83603ac27e', 'mmd_registry/services/structural_texture.py': '5a1e42d5eddce32927fd5e7a671011a69140e21f', 'mmd_registry/services/structural_transaction.py': '70bd0a5a7f8c73718c0e1f4ea5390766aec01145', 'mmd_registry/services/structural_transaction_plan.py': 'af98251c12fd1e8bde7db0c69e42f22af1b4a394', 'mmd_registry/services/structural_transaction_plan_apply.py': 'eb383efea7faaf27992f5560aa2c22b77a3e001d', 'mmd_registry/services/structural_transaction_plan_preview.py': 'e787a2b4046e7c2c4b9ccb805396f7404329ec70', 'mmd_registry/services/structural_vertex.py': '3882c7a3b4c65fa083e1ec9bd167b94c5e22ed67', 'mmd_registry/smart_cli.py': '5b6001d7e9c6dbf521faf50989c538e41a29de4f', 'mmd_registry/smart_part_confidence.py': '3d8f6f3b8076b94473b8376762fa59d099ad0a52', 'mmd_registry/smart_part_detection.py': 'd0c9d6a6882340e22803c1c978860197ed7bb30e', 'mmd_registry/smart_part_explainability.py': '7b62e97f2b7393f6a160e57ba8fd937aad4f8c12', 'mmd_registry/smart_parts.py': '004fcc5d5b701447842615fb158743c87e57fa99', 'mmd_registry/texture_path_semantics.py': 'e6430df5ac400452fe09642e509c96db4bca7247', 'mmd_registry/texture_portability.py': '083da4d9759fda622263e88f5cd1932fb06c6574', 'mmd_registry/texture_portability_cli.py': '97eb0a60077ec21b5bd7b743301d7b4125760764', 'mmd_registry/texture_rewrite.py': '419ea50425354968cf534bb1efd2bf29a45aec4a', 'mmd_registry/transaction_plan_cli.py': 'f0adab0120d892180a4fb2147334266a589d4ff6', 'mmd_registry/validator.py': 'a2d9674426cb5417154481f421c821109ef1f9a0'}, 'core_git_paths': {'mmd_registry/__init__.py': 'mmd_registry/__init__.py', 'mmd_registry/_smart_part_confidence.py': 'mmd_registry/_smart_part_confidence.py', 'mmd_registry/binary_reader.py': 'mmd_registry/binary_reader.py', 'mmd_registry/bone_cli.py': 'mmd_registry/bone_cli.py', 'mmd_registry/bone_details.py': 'mmd_registry/bone_details.py', 'mmd_registry/bone_explorer.py': 'mmd_registry/bone_explorer.py', 'mmd_registry/bone_hierarchy.py': 'mmd_registry/bone_hierarchy.py', 'mmd_registry/bone_names.py': 'mmd_registry/bone_names.py', 'mmd_registry/bone_search.py': 'mmd_registry/bone_search.py', 'mmd_registry/bone_semantic_inference.py': 'mmd_registry/bone_semantic_inference.py', 'mmd_registry/bone_semantic_resolver.py': 'mmd_registry/bone_semantic_resolver.py', 'mmd_registry/bone_semantics.py': 'mmd_registry/bone_semantics.py', 'mmd_registry/capabilities.py': 'mmd_registry/capabilities.py', 'mmd_registry/cli.py': 'mmd_registry/cli.py', 'mmd_registry/constants.py': 'mmd_registry/constants.py', 'mmd_registry/dependency_diagnostics.py': 'mmd_registry/dependency_diagnostics.py', 'mmd_registry/diagnostics.py': 'mmd_registry/diagnostics.py', 'mmd_registry/hashing.py': 'mmd_registry/hashing.py', 'mmd_registry/model_inspection.py': 'mmd_registry/model_inspection.py', 'mmd_registry/model_scanning.py': 'mmd_registry/model_scanning.py', 'mmd_registry/pmx/__init__.py': 'mmd_registry/pmx/__init__.py', 'mmd_registry/pmx/bone_reference_remap.py': 'mmd_registry/pmx/bone_reference_remap.py', 'mmd_registry/pmx/collection_transform.py': 'mmd_registry/pmx/collection_transform.py', 'mmd_registry/pmx/document.py': 'mmd_registry/pmx/document.py', 'mmd_registry/pmx/editing/__init__.py': 'mmd_registry/pmx/editing/__init__.py', 'mmd_registry/pmx/editing/audit.py': 'mmd_registry/pmx/editing/audit.py', 'mmd_registry/pmx/editing/catalog.py': 'mmd_registry/pmx/editing/catalog.py', 'mmd_registry/pmx/editing/diagnostics.py': 'mmd_registry/pmx/editing/diagnostics.py', 'mmd_registry/pmx/editing/engine.py': 'mmd_registry/pmx/editing/engine.py', 'mmd_registry/pmx/editing/errors.py': 'mmd_registry/pmx/editing/errors.py', 'mmd_registry/pmx/editing/explain.py': 'mmd_registry/pmx/editing/explain.py', 'mmd_registry/pmx/editing/json_loader.py': 'mmd_registry/pmx/editing/json_loader.py', 'mmd_registry/pmx/editing/numeric.py': 'mmd_registry/pmx/editing/numeric.py', 'mmd_registry/pmx/editing/operations.py': 'mmd_registry/pmx/editing/operations.py', 'mmd_registry/pmx/editing/output.py': 'mmd_registry/pmx/editing/output.py', 'mmd_registry/pmx/editing/path_policy.py': 'mmd_registry/pmx/editing/path_policy.py', 'mmd_registry/pmx/editing/plan.py': 'mmd_registry/pmx/editing/plan.py', 'mmd_registry/pmx/editing/preview.py': 'mmd_registry/pmx/editing/preview.py', 'mmd_registry/pmx/editing/template.py': 'mmd_registry/pmx/editing/template.py', 'mmd_registry/pmx/editing/validation.py': 'mmd_registry/pmx/editing/validation.py', 'mmd_registry/pmx/errors.py': 'mmd_registry/pmx/errors.py', 'mmd_registry/pmx/geometry_material_remap.py': 'mmd_registry/pmx/geometry_material_remap.py', 'mmd_registry/pmx/index_remap.py': 'mmd_registry/pmx/index_remap.py', 'mmd_registry/pmx/morph_display_remap.py': 'mmd_registry/pmx/morph_display_remap.py', 'mmd_registry/pmx/physics_reference_remap.py': 'mmd_registry/pmx/physics_reference_remap.py', 'mmd_registry/pmx/reader.py': 'mmd_registry/pmx/reader.py', 'mmd_registry/pmx/reference_diagnostics.py': 'mmd_registry/pmx/reference_diagnostics.py', 'mmd_registry/pmx/reference_graph.py': 'mmd_registry/pmx/reference_graph.py', 'mmd_registry/pmx/reference_model.py': 'mmd_registry/pmx/reference_model.py', 'mmd_registry/pmx/reference_queries.py': 'mmd_registry/pmx/reference_queries.py', 'mmd_registry/pmx/roundtrip.py': 'mmd_registry/pmx/roundtrip.py', 'mmd_registry/pmx/sections/__init__.py': 'mmd_registry/pmx/sections/__init__.py', 'mmd_registry/pmx/sections/bones.py': 'mmd_registry/pmx/sections/bones.py', 'mmd_registry/pmx/sections/display_frames.py': 'mmd_registry/pmx/sections/display_frames.py', 'mmd_registry/pmx/sections/geometry.py': 'mmd_registry/pmx/sections/geometry.py', 'mmd_registry/pmx/sections/header.py': 'mmd_registry/pmx/sections/header.py', 'mmd_registry/pmx/sections/joints.py': 'mmd_registry/pmx/sections/joints.py', 'mmd_registry/pmx/sections/materials.py': 'mmd_registry/pmx/sections/materials.py', 'mmd_registry/pmx/sections/morphs.py': 'mmd_registry/pmx/sections/morphs.py', 'mmd_registry/pmx/sections/rigid_bodies.py': 'mmd_registry/pmx/sections/rigid_bodies.py', 'mmd_registry/pmx/sections/soft_bodies.py': 'mmd_registry/pmx/sections/soft_bodies.py', 'mmd_registry/pmx/sections/textures.py': 'mmd_registry/pmx/sections/textures.py', 'mmd_registry/pmx/structural_bone_insertion.py': 'mmd_registry/pmx/structural_bone_insertion.py', 'mmd_registry/pmx/structural_capacity.py': 'mmd_registry/pmx/structural_capacity.py', 'mmd_registry/pmx/structural_coordinated_insertion.py': 'mmd_registry/pmx/structural_coordinated_insertion.py', 'mmd_registry/pmx/structural_insert_intent.py': 'mmd_registry/pmx/structural_insert_intent.py', 'mmd_registry/pmx/structural_invariants.py': 'mmd_registry/pmx/structural_invariants.py', 'mmd_registry/pmx/structural_material_insertion.py': 'mmd_registry/pmx/structural_material_insertion.py', 'mmd_registry/pmx/structural_morph_insertion.py': 'mmd_registry/pmx/structural_morph_insertion.py', 'mmd_registry/pmx/structural_orchestrator.py': 'mmd_registry/pmx/structural_orchestrator.py', 'mmd_registry/pmx/structural_output.py': 'mmd_registry/pmx/structural_output.py', 'mmd_registry/pmx/structural_preview.py': 'mmd_registry/pmx/structural_preview.py', 'mmd_registry/pmx/structural_reference_shift.py': 'mmd_registry/pmx/structural_reference_shift.py', 'mmd_registry/pmx/structural_rigid_body_insertion.py': 'mmd_registry/pmx/structural_rigid_body_insertion.py', 'mmd_registry/pmx/structural_texture_insertion.py': 'mmd_registry/pmx/structural_texture_insertion.py', 'mmd_registry/pmx/structural_transaction_composition.py': 'mmd_registry/pmx/structural_transaction_composition.py', 'mmd_registry/pmx/structural_transaction_dependency.py': 'mmd_registry/pmx/structural_transaction_dependency.py', 'mmd_registry/pmx/structural_transaction_insertion.py': 'mmd_registry/pmx/structural_transaction_insertion.py', 'mmd_registry/pmx/structural_transaction_placement.py': 'mmd_registry/pmx/structural_transaction_placement.py', 'mmd_registry/pmx/structural_transaction_preflight.py': 'mmd_registry/pmx/structural_transaction_preflight.py', 'mmd_registry/pmx/structural_transaction_preview.py': 'mmd_registry/pmx/structural_transaction_preview.py', 'mmd_registry/pmx/structural_transaction_reference.py': 'mmd_registry/pmx/structural_transaction_reference.py', 'mmd_registry/pmx/structural_vertex_insertion.py': 'mmd_registry/pmx/structural_vertex_insertion.py', 'mmd_registry/pmx/transaction_plan.py': 'mmd_registry/pmx/transaction_plan.py', 'mmd_registry/pmx/validation.py': 'mmd_registry/pmx/validation.py', 'mmd_registry/pmx/writer.py': 'mmd_registry/pmx/writer.py', 'mmd_registry/reporting.py': 'mmd_registry/reporting.py', 'mmd_registry/rig_analysis.py': 'mmd_registry/rig_analysis.py', 'mmd_registry/rig_cli.py': 'mmd_registry/rig_cli.py', 'mmd_registry/rig_diagnostics.py': 'mmd_registry/rig_diagnostics.py', 'mmd_registry/services/__init__.py': 'mmd_registry/services/__init__.py', 'mmd_registry/services/_smart_inspection.py': 'mmd_registry/services/_smart_inspection.py', 'mmd_registry/services/structural_authoring_builder.py': 'mmd_registry/services/structural_authoring_builder.py', 'mmd_registry/services/structural_authoring_catalog.py': 'mmd_registry/services/structural_authoring_catalog.py', 'mmd_registry/services/structural_authoring_diff.py': 'mmd_registry/services/structural_authoring_diff.py', 'mmd_registry/services/structural_authoring_formatter.py': 'mmd_registry/services/structural_authoring_formatter.py', 'mmd_registry/services/structural_authoring_selector.py': 'mmd_registry/services/structural_authoring_selector.py', 'mmd_registry/services/structural_bone.py': 'mmd_registry/services/structural_bone.py', 'mmd_registry/services/structural_material.py': 'mmd_registry/services/structural_material.py', 'mmd_registry/services/structural_morph.py': 'mmd_registry/services/structural_morph.py', 'mmd_registry/services/structural_reference.py': 'mmd_registry/services/structural_reference.py', 'mmd_registry/services/structural_rigid_body.py': 'mmd_registry/services/structural_rigid_body.py', 'mmd_registry/services/structural_texture.py': 'mmd_registry/services/structural_texture.py', 'mmd_registry/services/structural_transaction.py': 'mmd_registry/services/structural_transaction.py', 'mmd_registry/services/structural_transaction_plan.py': 'mmd_registry/services/structural_transaction_plan.py', 'mmd_registry/services/structural_transaction_plan_apply.py': 'mmd_registry/services/structural_transaction_plan_apply.py', 'mmd_registry/services/structural_transaction_plan_preview.py': 'mmd_registry/services/structural_transaction_plan_preview.py', 'mmd_registry/services/structural_vertex.py': 'mmd_registry/services/structural_vertex.py', 'mmd_registry/smart_cli.py': 'mmd_registry/smart_cli.py', 'mmd_registry/smart_part_confidence.py': 'mmd_registry/smart_part_confidence.py', 'mmd_registry/smart_part_detection.py': 'mmd_registry/smart_part_detection.py', 'mmd_registry/smart_part_explainability.py': 'mmd_registry/smart_part_explainability.py', 'mmd_registry/smart_parts.py': 'mmd_registry/smart_parts.py', 'mmd_registry/texture_path_semantics.py': 'mmd_registry/texture_path_semantics.py', 'mmd_registry/texture_portability.py': 'mmd_registry/texture_portability.py', 'mmd_registry/texture_portability_cli.py': 'mmd_registry/texture_portability_cli.py', 'mmd_registry/texture_rewrite.py': 'mmd_registry/texture_rewrite.py', 'mmd_registry/transaction_plan_cli.py': 'mmd_registry/transaction_plan_cli.py', 'mmd_registry/validator.py': 'mmd_registry/validator.py'}, 'git_exe': 'C:\\Program Files\\Git\\cmd\\git.exe', 'git_exe_sha256': '54194a1af7cfb6730448ce14b8f2c1dddd9f950b7f995dc351c1ed16eb179249', 'canonical_config_sha256': '0b6d4c2e1f0441d8f24f63755dc0b35aec86f19af5aa524f9de92e026ddd0b0c', 'cp19_config_sha256': '74c63b4eae3533b3ff4c0e285897778464d6c04815c33457729279ded1e2a947'}
    CAP = 1048576
    def require(ok, reason):
        if not ok:
            raise RuntimeError(reason)
    def sha(raw):
        return hashlib.sha256(raw).hexdigest()
    """Bounded, offline Git plumbing for CP23-R1R. Never mutates a repository.

    The caller supplies filesystem guards and tracked reads. Git reads are confined
    to the explicit standalone object store after redirect/config checks. The
    caller must repeat tracked metadata checks after all lanes have completed.
    """

    import hashlib
    import os
    from pathlib import Path
    import re
    import subprocess
    import threading


    class Hold(RuntimeError):
        pass


    _OID = re.compile(r'[0-9a-f]{40}\Z')
    _KNOWN = {
        'cp19_parent': '35b3a30962465a759c15fcd9780e8c47022b1928',
        'cp19': '006803c2bdd6be566c53af40af0232fe229185c1',
        'cp20': '6dcd89b8b6230d95cb076419793b774353982f71',
        'cp22': '8018da337ac41a154da268f137cd890bdc271e52',
        'prior_head': '90140c9064392540c9a26e71ea7fc163a43ebd58',
    }


    class Repo:
        def __init__(self, git_exe: Path, gitdir: Path, worktree: Path | None,
                     cwd: Path, read: callable, guard: callable):
            self.git_exe, self.gitdir = Path(git_exe), Path(gitdir)
            self.worktree = Path(worktree) if worktree is not None else None
            self.cwd, self.read, self.guard = Path(cwd), read, guard
            if any(not path.is_absolute() for path in
                   [self.git_exe, self.gitdir, self.cwd] + ([self.worktree] if self.worktree else [])):
                raise Hold('ABSOLUTE_PATHS_REQUIRED')
            self._ready = False
            self._metadata = {}
            self._config = {}
            self._shallow = {'present': False, 'boundaries': []}
            self._scan_state, self._head, self._version = None, None, None
            self._inventory_complete = False
            self.commands = []
            self._env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
            self._env.update({
                'GIT_OPTIONAL_LOCKS': '0', 'GIT_NO_REPLACE_OBJECTS': '1',
                'GIT_NO_LAZY_FETCH': '1', 'GIT_CONFIG_NOSYSTEM': '1',
                'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_SYSTEM': os.devnull,
                'GIT_ALLOW_PROTOCOL': '', 'GIT_PROTOCOL_FROM_USER': '0',
                'GIT_TERMINAL_PROMPT': '0',
            })

        @staticmethod
        def _oid(oid):
            if not isinstance(oid, str) or not _OID.fullmatch(oid):
                raise Hold('INVALID_FULL_SHA1_OID')
            return oid

        def _prefix(self, repo=True):
            prefix = [str(self.git_exe), '--no-pager', '--no-optional-locks',
                      '--no-replace-objects', '--no-lazy-fetch']
            for value in ('protocol.allow=never', 'core.fsmonitor=false',
                          'core.commitGraph=false', 'core.multiPackIndex=false',
                          'gc.auto=0', 'maintenance.auto=false',
                          'safe.directory=' + str(self.worktree or self.gitdir)):
                prefix.extend(['-c', value])
            if repo:
                prefix.append('--git-dir=' + str(self.gitdir))
            return prefix

        def _run(self, args, data=None, cap=1024 * 1024, repo=True, allowed=(0,)):
            """Only private fixed plumbing callers reach this bounded executor."""
            argv = self._prefix(repo) + list(args)
            buffers = [bytearray(), bytearray()]
            exceeded = threading.Event()
            try:
                proc = subprocess.Popen(argv, cwd=self.cwd, env=self._env,
                                        shell=False, stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except OSError as exc:
                raise Hold('GIT_START_ERROR:' + type(exc).__name__) from exc

            def consume(stream, index, limit):
                try:
                    while True:
                        chunk = stream.read(65536)
                        if not chunk:
                            break
                        remaining = limit - len(buffers[index])
                        buffers[index].extend(chunk[:max(0, remaining)])
                        if len(chunk) > remaining:
                            exceeded.set()
                            proc.kill()
                            break
                finally:
                    stream.close()

            readers = [threading.Thread(target=consume, args=(proc.stdout, 0, cap), daemon=True),
                       threading.Thread(target=consume, args=(proc.stderr, 1, 65536), daemon=True)]
            for reader in readers:
                reader.start()
            writer = None
            if data is not None:
                def supply_input():
                    try:
                        proc.stdin.write(data)
                    except (BrokenPipeError, OSError):
                        pass
                    finally:
                        try:
                            proc.stdin.close()
                        except (BrokenPipeError, OSError):
                            pass
                writer = threading.Thread(target=supply_input, daemon=True)
                writer.start()
            timed_out = False
            try:
                proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                timed_out = True
                proc.kill()
                proc.wait(timeout=10)
            finally:
                for reader in readers:
                    reader.join(timeout=10)
                if writer is not None:
                    writer.join(timeout=10)
            raw, err = bytes(buffers[0]), bytes(buffers[1])
            self.commands.append({'command': args[0], 'returncode': proc.returncode,
                                  'stdout_bytes': len(raw), 'stderr_bytes': len(err)})
            if timed_out:
                raise Hold('GIT_TIMEOUT')
            if exceeded.is_set() or any(reader.is_alive() for reader in readers) or (writer and writer.is_alive()):
                raise Hold('GIT_OUTPUT_LIMIT')
            if proc.returncode not in allowed or err:
                detail = err.decode('utf-8', 'replace').strip()[:400]
                raise Hold('GIT_ERROR:' + str(proc.returncode) + ':' + detail)
            return proc.returncode, raw

        def _read_metadata(self, path, cap=1024 * 1024):
            raw = self.read(path, cap)
            self._metadata[str(path.relative_to(self.gitdir))] = {
                'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
            return raw

        @staticmethod
        def _entry_identity(path, kind):
            # Owner's Windows filesystem supports normal reads/GetFileAttributesW
            # but has rejected Path.lstat(). Never reintroduce that API through
            # stat(follow_symlinks=False) on Windows.
            if os.name == 'nt':
                import ctypes
                from ctypes import wintypes

                class FileTime(ctypes.Structure):
                    _fields_ = [('low', wintypes.DWORD), ('high', wintypes.DWORD)]

                class AttributeData(ctypes.Structure):
                    _fields_ = [('attributes', wintypes.DWORD),
                                ('creation', FileTime), ('access', FileTime),
                                ('write', FileTime), ('size_high', wintypes.DWORD),
                                ('size_low', wintypes.DWORD)]

                kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                get_attributes = kernel.GetFileAttributesExW
                get_attributes.argtypes = [wintypes.LPCWSTR, ctypes.c_int,
                                           ctypes.POINTER(AttributeData)]
                get_attributes.restype = wintypes.BOOL
                name = str(path)
                if not name.startswith('\\\\?\\'):
                    name = ('\\\\?\\UNC\\' + name[2:] if name.startswith('\\\\')
                            else '\\\\?\\' + name)
                data = AttributeData()
                if not get_attributes(name, 0, ctypes.byref(data)):
                    raise Hold('WIN32_ATTRIBUTE_READ_ERROR:' + str(ctypes.get_last_error()))
                # Access time changes during legitimate reads and is not compared.
                return [kind, (data.size_high << 32) | data.size_low,
                        (data.write.high << 32) | data.write.low,
                        (data.creation.high << 32) | data.creation.low,
                        data.attributes]
            info = path.stat(follow_symlinks=False)
            return [kind, info.st_size, info.st_mtime_ns, info.st_ino]

        def _scan(self):
            """Bounded full metadata/store reparse walk; no file data is executed."""
            result, count, directory_count = {}, 0, 0

            def walk_error(exc):
                raise Hold('GITDIR_WALK_ERROR:' + type(exc).__name__) from exc

            for parent, directories, files in os.walk(self.gitdir, followlinks=False, onerror=walk_error):
                paths = [(Path(parent), 'dir')]
                paths.extend((Path(parent) / name, 'file') for name in files)
                for name in directories:
                    self.guard(Path(parent) / name, 'dir')
                directory_count += 1
                if directory_count > 10000:
                    raise Hold('GITDIR_DIRECTORY_LIMIT')
                for path, kind in paths:
                    count += 1
                    if count > 250000:
                        raise Hold('GITDIR_ENTRY_LIMIT')
                    self.guard(path, kind)
                    result[str(path.relative_to(self.gitdir))] = self._entry_identity(path, kind)
            return result

        def _preflight(self):
            if self._ready:
                return
            self.guard(self.git_exe, 'file')
            self.guard(self.cwd, 'dir')
            self.guard(self.gitdir, 'dir')
            if self.worktree is not None:
                self.guard(self.worktree, 'dir')
                if self.gitdir != self.worktree / '.git':
                    raise Hold('NONCANONICAL_GITDIR')
            # Guard checks every ancestor and the Windows reparse attribute.
            self._scan_state = self._scan()
            self.guard(self.gitdir / 'objects', 'dir')
            scanned_names = {name.casefold() if os.name == 'nt' else name
                             for name in self._scan_state}
            for relative, reason in (
                    ('commondir', 'GIT_COMMONDIR'), ('config.worktree', 'WORKTREE_CONFIG'),
                    ('objects/info/alternates', 'GIT_ALTERNATES'),
                    ('objects/info/http-alternates', 'GIT_HTTP_ALTERNATES'),
                    ('info/grafts', 'GIT_GRAFTS')):
                key = str(Path(relative))
                if (key.casefold() if os.name == 'nt' else key) in scanned_names:
                    raise Hold(reason)
            self._read_metadata(self.gitdir / 'config')
            # --file and --no-includes ensure that even malicious includeIf syntax
            # cannot read an external config during safety inspection.
            _, output = self._run(['config', '--no-includes', '--null', '--file',
                                   str(self.gitdir / 'config'), '--list'], repo=False)
            for record in output.split(b'\0'):
                if not record:
                    continue
                key, separator, value = record.partition(b'\n')
                try:
                    key = key.decode('ascii').lower()
                    value = value.decode('utf-8', 'strict') if separator else 'true'
                except UnicodeError as exc:
                    raise Hold('CONFIG_ENCODING') from exc
                if key == 'include.path' or key.startswith('includeif.'):
                    raise Hold('CONFIG_INCLUDE')
                self._config.setdefault(key, []).append(value)
            if self._config.get('extensions.objectformat', ['sha1'])[-1].lower() != 'sha1':
                raise Hold('NON_SHA1_OBJECT_FORMAT')
            for key in self._config:
                if key.startswith('extensions.') and key not in ('extensions.objectformat', 'extensions.partialclone'):
                    raise Hold('UNSUPPORTED_GIT_EXTENSION:' + key)
            bare = self._config.get('core.bare', ['false'])[-1].lower()
            if bare not in ('true', 'false', 'yes', 'no', 'on', 'off', '1', '0'):
                raise Hold('CONFIG_BARE_INVALID')
            if (bare in ('true', 'yes', 'on', '1')) != (self.worktree is None):
                raise Hold('BARE_MODE_MISMATCH')
            if 'core.worktree' in self._config:
                configured = self._config['core.worktree'][-1]
                configured_path = Path(configured)
                if not configured_path.is_absolute():
                    configured_path = self.gitdir / configured_path
                if self.worktree is None or os.path.normcase(os.path.abspath(configured_path)) != os.path.normcase(str(self.worktree.absolute())):
                    raise Hold('CONFIG_WORKTREE_REDIRECT')
            for relative in ('HEAD', 'packed-refs', 'shallow'):
                path = self.gitdir / relative
                key = str(Path(relative))
                if key in self._scan_state and self._scan_state[key][0] == 'file':
                    raw = self._read_metadata(path)
                    if relative == 'shallow':
                        try:
                            boundaries = raw.decode('ascii').splitlines()
                        except UnicodeError as exc:
                            raise Hold('SHALLOW_INVALID') from exc
                        if not boundaries or any(not _OID.fullmatch(x) for x in boundaries):
                            raise Hold('SHALLOW_INVALID')
                        self._shallow = {'present': True, 'boundaries': boundaries,
                                         'sha256': hashlib.sha256(raw).hexdigest()}
            refs = self.gitdir / 'refs'
            if 'refs' in self._scan_state and self._scan_state['refs'][0] == 'dir':
                for parent, _, files in os.walk(refs, followlinks=False):
                    for name in files:
                        self._read_metadata(Path(parent) / name)
            self._ready = True

        def _batch(self, oids, cap_each):
            unique = list(dict.fromkeys(self._oid(oid) for oid in oids))
            if not unique:
                return {}
            if len(unique) > 8192 or not 0 < cap_each <= 16 * 1024 * 1024:
                raise Hold('OBJECT_BATCH_LIMIT')
            _, raw = self._run(['cat-file', '--batch'],
                               data=('\n'.join(unique) + '\n').encode('ascii'),
                               cap=len(unique) * (cap_each + 128))
            result, cursor = {}, 0
            for oid in unique:
                end = raw.find(b'\n', cursor, cursor + 256)
                if end < 0:
                    raise Hold('BATCH_HEADER_INVALID')
                fields = raw[cursor:end].split(b' ')
                cursor = end + 1
                if fields == [oid.encode('ascii'), b'missing']:
                    result[oid] = {'status': 'MISSING_LOCAL_OBJECT_NO_FETCH'}
                    continue
                if len(fields) != 3 or fields[0] != oid.encode('ascii') or not fields[2].isdigit():
                    raise Hold('BATCH_RESPONSE_INVALID')
                size = int(fields[2])
                if size > cap_each or cursor + size >= len(raw) or raw[cursor + size] != 10:
                    raise Hold('OBJECT_SIZE_OR_FRAMING_LIMIT')
                payload = raw[cursor:cursor + size]
                cursor += size + 1
                header = fields[1] + b' ' + fields[2] + b'\0'
                if hashlib.sha1(header + payload).hexdigest() != oid:
                    raise Hold('OBJECT_SHA1_MISMATCH:' + oid)
                result[oid] = {'status': 'AVAILABLE', 'type': fields[1].decode('ascii'),
                               'size': size, 'raw': payload,
                               'sha256': hashlib.sha256(payload).hexdigest(),
                               'object_sha1_verified': True}
            if cursor != len(raw):
                raise Hold('BATCH_TRAILING_BYTES')
            return result

        def inventory(self, pins: dict[str, str]) -> dict:
            if not isinstance(pins, dict) or not pins or len(pins) > 32:
                raise Hold('PIN_SET_INVALID')
            for oid in pins.values():
                self._oid(oid)
            self._preflight()
            _, version = self._run(['--version'], cap=256, repo=False)
            self._version = version.decode('ascii', 'strict').strip()
            if not self._version.startswith('git version '):
                raise Hold('GIT_VERSION_INVALID')
            # A detached historical bare object store may have an unborn symbolic
            # HEAD. R1R's authority is pinned CP19 object IDs, not the bare default
            # branch. Canonical worktree HEAD remains strictly required.
            if self.worktree is None:
                head = None
                head_resolution = 'BARE_HEAD_NOT_REQUIRED_FOR_EXACT_PINNED_OBJECTS'
            else:
                _, raw_head = self._run(['rev-parse', '--verify', 'HEAD^{commit}'], cap=128)
                try:
                    head = self._oid(raw_head.decode('ascii').strip())
                except UnicodeError as exc:
                    raise Hold('HEAD_INVALID') from exc
                head_resolution = 'CANONICAL_HEAD_RESOLVED'
            self._head = head
            objects = self._batch(list(pins.values()) + ([head] if head else []), 1024 * 1024)
            for oid, item in objects.items():
                if item['status'] != 'AVAILABLE':
                    continue
                payload = item.pop('raw')
                if item['type'] != 'commit':
                    item['status'] = 'TYPE_MISMATCH_NOT_COMMIT'
                    continue
                headers = payload.split(b'\n\n', 1)[0].splitlines()
                trees = [x[5:].decode('ascii') for x in headers if x.startswith(b'tree ')]
                parents = [x[7:].decode('ascii') for x in headers if x.startswith(b'parent ')]
                if len(trees) != 1:
                    raise Hold('COMMIT_TREE_INVALID')
                self._oid(trees[0])
                for parent in parents:
                    self._oid(parent)
                item.update(status='AVAILABLE_COMMIT', tree=trees[0], parents=parents)
            roles = {}
            for label, oid in pins.items():
                name = str(label).lower()
                for role, known in _KNOWN.items():
                    if oid == known or name == role or name == role + '_pin' or name == role + '_commit':
                        roles[role] = oid
            if head is not None:
                roles['head'] = head
            pair_roles = [('cp19_parent', 'cp19'), ('cp19', 'cp20'), ('cp19', 'cp22'),
                          ('cp19', 'head'), ('cp20', 'cp22'), ('cp20', 'head'), ('cp22', 'head')]
            ancestry, seen = [], set()
            for first, second in pair_roles:
                if first not in roles or second not in roles:
                    continue
                ancestor, descendant = roles[first], roles[second]
                if (ancestor, descendant) in seen:
                    continue
                seen.add((ancestor, descendant))
                row = {'ancestor': ancestor, 'descendant': descendant, 'returncode': None}
                statuses = [objects[x]['status'] for x in (ancestor, descendant)]
                if any(x == 'MISSING_LOCAL_OBJECT_NO_FETCH' for x in statuses):
                    row['status'] = 'NOT_ATTESTED_MISSING_OBJECT'
                elif any(x != 'AVAILABLE_COMMIT' for x in statuses):
                    row['status'] = 'ERROR_OBJECT_NOT_COMMIT'
                else:
                    rc, _ = self._run(['merge-base', '--is-ancestor', ancestor, descendant], cap=1024, allowed=(0, 1))
                    row['returncode'] = rc
                    row['status'] = ('ANCESTOR' if rc == 0 else
                                     'ANCESTRY_INDETERMINATE_SHALLOW' if self._shallow['present'] else 'NONANCESTOR')
                ancestry.append(row)
            self._inventory_complete = True
            return {'head': head, 'head_resolution': head_resolution,
                    'git_version': self._version, 'pins': dict(pins), 'objects': objects,
                    'ancestry': ancestry, 'shallow': dict(self._shallow),
                    'prior_head_match': head == roles['prior_head'] if 'prior_head' in roles else None,
                    'metadata': dict(self._metadata),
                    'config': {'includes': False, 'object_format': 'sha1',
                               'bare': self.worktree is None,
                               'promisor_config_present': any('promisor' in key or key == 'extensions.partialclone' for key in self._config)},
                    'commands': list(self.commands),
                    'writes': '0_BY_RUNNER_DESIGN_NOT_OS_ATTESTATION'}

        def tree(self, commit: str, paths: list[str]) -> dict:
            self._oid(commit)
            if not paths or len(paths) > 128:
                raise Hold('TREE_PATH_SET_INVALID')
            for path in paths:
                if (not isinstance(path, str) or not path or path.startswith(('/', '\\', ':'))
                        or '\\' in path or '\0' in path or any(x in path for x in '*?[]')
                        or any(x in ('', '.', '..') for x in path.split('/'))):
                    raise Hold('TREE_PATH_INVALID')
            self._preflight()
            _, raw = self._run(['ls-tree', '-r', '-z', commit, '--', *paths], cap=16 * 1024 * 1024)
            result = {}
            for record in raw.split(b'\0'):
                if not record:
                    continue
                header, separator, raw_path = record.partition(b'\t')
                fields = header.split(b' ')
                if not separator or len(fields) != 3:
                    raise Hold('TREE_FRAMING_INVALID')
                try:
                    mode, kind, oid = [x.decode('ascii') for x in fields]
                    path = raw_path.decode('utf-8', 'strict')
                except UnicodeError as exc:
                    raise Hold('TREE_ENCODING_INVALID') from exc
                self._oid(oid)
                if mode not in ('100644', '100755') or kind != 'blob':
                    raise Hold('TREE_UNSAFE_MODE:' + mode + ':' + kind)
                if not any(path == target or path.startswith(target.rstrip('/') + '/') for target in paths):
                    raise Hold('TREE_OUTSIDE_REQUESTED_PATH')
                if path in result:
                    raise Hold('TREE_DUPLICATE_PATH')
                result[path] = {'oid': oid, 'mode': mode, 'type': kind}
            return result

        def blobs(self, oids: list[str], cap_each=1048576) -> dict:
            self._preflight()
            objects = self._batch(oids, cap_each)
            result = {}
            for oid, item in objects.items():
                if item['status'] != 'AVAILABLE' or item['type'] != 'blob':
                    raise Hold('BLOB_MISSING_OR_WRONG_TYPE:' + oid)
                result[oid] = item['raw']
            return result

        def named_refs(self) -> dict:
            self._preflight()
            output = {}
            for label, ref in [('cp20','refs/heads/feature/cp20-r6t-isolated-landing'),
                               ('cp22','refs/heads/feature/cp22-r15-source-only-mc-a0')]:
                rc, raw = self._run(['rev-parse','--verify','--quiet',ref+'^{commit}'], cap=128, allowed=(0,1))
                if rc == 1:
                    output[label] = {'ref':ref,'status':'MISSING_REF_NO_FALLBACK'}
                else:
                    oid = self._oid(raw.decode('ascii','strict').strip())
                    output[label] = {'ref':ref,'oid':oid,'expected':_KNOWN[label],
                                     'status':'MATCH_PIN' if oid==_KNOWN[label] else 'REF_DRIFT'}
            return output

        def postflight(self) -> dict:
            """Detect metadata/ref/store changes and reparse swaps after all reads."""
            if not self._ready or not self._inventory_complete or (self.worktree is not None and self._head is None):
                raise Hold('POSTFLIGHT_WITHOUT_INVENTORY')
            if self._scan() != self._scan_state:
                raise Hold('POSTFLIGHT_GIT_METADATA_OR_STORE_CHANGED')
            for relative, expected in self._metadata.items():
                raw = self.read(self.gitdir / relative, 1024 * 1024)
                actual = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
                if actual != expected:
                    raise Hold('POSTFLIGHT_METADATA_CHANGED:' + relative)
            if self.worktree is not None:
                _, raw = self._run(['rev-parse', '--verify', 'HEAD^{commit}'], cap=128)
                if raw.decode('ascii', 'strict').strip() != self._head:
                    raise Hold('POSTFLIGHT_HEAD_CHANGED')
            # For bare repositories, the HEAD text and all refs remain bound by the
            # exact pre/post file+metadata inventory, without requiring resolution.
            return {'metadata_unchanged': True, 'head_unchanged': True,
                    'refs_inventory_unchanged': True, 'object_store_stat_inventory_unchanged': True,
                    'reparse_rescan': True, 'git_version': self._version,
                    'commands_count': len(self.commands),
                    'writes': '0_BY_RUNNER_DESIGN_NOT_OS_ATTESTATION',
                    'limitation': 'PRE_POST_SNAPSHOTS_DO_NOT_ELIMINATE_HOSTILE_CONCURRENT_TOCTOU'}

    def inside(path, roots):
        return any(path == r or path.is_relative_to(r) for r in roots)

    def no_reparse(path):
        path = Path(os.path.abspath(path))
        require(not str(path).startswith('\\\\'), 'UNC_NOT_ALLOWED')
        for q in [*reversed(path.parents), path]:
            if os.name == 'nt':
                require(not (win_attributes(q) & 0x400), 'REPARSE:'+str(q))
            else:
                s = q.lstat()
                require(not stat.S_ISLNK(s.st_mode), 'REPARSE:'+str(q))
        return path

    def win_attributes(path):
        # Preserve R1P V3's known Owner-host compatibility fix: no Path.lstat on Windows.
        import ctypes as c
        k = c.WinDLL('kernel32', use_last_error=True)
        get = k.GetFileAttributesW
        get.argtypes = [c.c_wchar_p]
        get.restype = c.c_uint32
        value = get(str(path))
        if value == 0xFFFFFFFF:
            err = c.get_last_error()
            if err in (2,3):
                raise FileNotFoundError(err, 'WIN_ATTRIBUTES', str(path))
            raise OSError(err, 'WIN_ATTRIBUTES', str(path))
        return value

    def open_handle(path, write=False):
        """Windows: no write/delete sharing; verify final path before consuming bytes.
        Git subprocess multi-file access still has a documented concurrent-race limit.
        """
        path = Path(os.path.abspath(path))
        no_reparse(path.parent if write else path)
        if os.name != 'nt':
            return os.open(path, (os.O_WRONLY|os.O_CREAT|os.O_EXCL if write else os.O_RDONLY) | getattr(os,'O_NOFOLLOW',0), 0o600)
        import ctypes as c
        from ctypes import wintypes as w
        import msvcrt
        k = c.WinDLL('kernel32', use_last_error=True)
        k.CreateFileW.argtypes = [w.LPCWSTR,w.DWORD,w.DWORD,w.LPVOID,w.DWORD,w.DWORD,w.HANDLE]
        k.CreateFileW.restype = w.HANDLE
        k.GetFinalPathNameByHandleW.argtypes = [w.HANDLE,w.LPWSTR,w.DWORD,w.DWORD]
        k.GetFinalPathNameByHandleW.restype = w.DWORD
        k.CloseHandle.argtypes = [w.HANDLE]
        handle = k.CreateFileW(str(path), 0x40000000 if write else 0x80000000,
                               1, None, 1 if write else 3, 0x00200000|0x08000000, None)
        if handle == c.c_void_p(-1).value:
            raise OSError(c.get_last_error(), 'CREATEFILE_FAILED', str(path))
        try:
            buf = c.create_unicode_buffer(32768)
            n = k.GetFinalPathNameByHandleW(handle, buf, len(buf), 0)
            final = buf.value.removeprefix('\\\\?\\')
            require(0 < n < len(buf) and final.casefold() == str(path).casefold(), 'HANDLE_PATH_MISMATCH:'+str(path))
            no_reparse(path)
            fd = msvcrt.open_osfhandle(handle, (os.O_WRONLY if write else os.O_RDONLY)|os.O_BINARY)
            handle = None
            return fd
        finally:
            if handle is not None:
                k.CloseHandle(handle)

    class Reads:
        def __init__(self, roots):
            self.roots = [Path(os.path.abspath(x)) for x in roots]
            self.files = {}
            self.lock = threading.Lock()

        def guard(self, path, kind='dir'):
            path = Path(os.path.abspath(path))
            require(inside(path,self.roots), 'OUTSIDE_APPROVED_ROOT:'+str(path))
            path = no_reparse(path)
            if os.name == 'nt':
                require(bool(win_attributes(path)&0x10) == (kind=='dir'), 'PATH_KIND:'+str(path))
            else:
                require(path.is_dir() if kind=='dir' else path.is_file(), 'PATH_KIND:'+str(path))
            return path

        def read(self, path, cap=12*CAP):
            path = self.guard(path,'file')
            with os.fdopen(open_handle(path), 'rb') as f:
                pre = os.fstat(f.fileno())
                require(stat.S_ISREG(pre.st_mode) and pre.st_size <= cap, 'READ_SIZE_OR_KIND:'+str(path))
                raw = f.read(cap+1)
                post = os.fstat(f.fileno())
            identity = (pre.st_dev,pre.st_ino,pre.st_size,pre.st_mtime_ns)
            require(identity == (post.st_dev,post.st_ino,post.st_size,post.st_mtime_ns) and len(raw)==pre.st_size,
                    'FILE_CHANGED_DURING_READ:'+str(path))
            self.guard(path,'file')
            record = {'sha256':sha(raw),'bytes':len(raw),'identity':identity}
            with self.lock:
                old = self.files.get(str(path))
                require(old is None or old == record, 'INPUT_CHANGED:'+str(path))
                self.files[str(path)] = record
            return raw

        def postflight(self):
            for p in list(self.files):
                self.read(Path(p), max(self.files[p]['bytes'],1))
            return {'unchanged_files':len(self.files),'method':'HANDLE_READ_SHA256_AND_FILE_ID_PRE_POST',
                    'limitation':'NO_OS_WIDE_WRITE_ATTESTATION; Git multi-file race and code already in memory are not attested'}


    try:
        _canonical = Path(_contract['canonical_root'])
        _bare = Path(_contract['cp19_bare'])
        _source_root = Path(_contract['source_root'])
        _gitexe = Path(_contract['git_exe'])
        _repo_arg = Path(os.path.abspath(repo))
        require(os.path.normcase(str(_repo_arg)) == os.path.normcase(str(_canonical)),
                'R1S_EXACT_CANONICAL_REQUIRED')
        _io = Reads([_canonical, _bare, _source_root, _gitexe.parent])
        _io.guard(_canonical)
        _io.guard(_bare)
        _io.guard(_source_root)
        require(sha(_io.read(_gitexe, 64 * CAP)) == _contract['git_exe_sha256'],
                'R1S_GIT_EXECUTABLE_SHA')
        require(sha(_io.read(_canonical / '.git' / 'config', CAP)) == _contract['canonical_config_sha256'],
                'R1S_CANONICAL_CONFIG_CHANGED')
        require(sha(_io.read(_bare / 'config', CAP)) == _contract['cp19_config_sha256'],
                'R1S_BARE_CONFIG_CHANGED')
        # Canonical-only cwd. Bare Git is read-only via explicit --git-dir.
        _canonical_git = Repo(_gitexe, _canonical / '.git', _canonical, _source_root, _io.read, _io.guard)
        _bare_git = Repo(_gitexe, _bare, None, _source_root, _io.read, _io.guard)
        _anchors = {'cp19_parent': PIN, 'cp19': '006803c2bdd6be566c53af40af0232fe229185c1'}
        _can = _canonical_git.inventory(_anchors)
        _base = _bare_git.inventory(_anchors)
        _core_commit = '006803c2bdd6be566c53af40af0232fe229185c1'
        require(_base['objects'][PIN]['status'] == 'AVAILABLE_COMMIT'
                and _base['objects'][_core_commit]['status'] == 'AVAILABLE_COMMIT'
                and PIN in _base['objects'][_core_commit]['parents'],
                'R1S_CP19_RAW_PARENT_OBJECT_LINK_REQUIRED')
        # Canonical missing PIN is recorded by inventory, never inferred from
        # _base. No conditional below equates the two object stores.
        _paths = sorted(_contract['core_git_paths'].values())
        _baseline_tree = _bare_git.tree(_core_commit, _paths)
        _head = _can['head']
        _head_tree = _canonical_git.tree(_head, _paths)
        _head_blobs = _canonical_git.blobs(sorted({x['oid'] for x in _head_tree.values()}), cap_each=CAP)
        # External CP19 bare is a read-only historical reference, never an
        # operational source root. Its Git OID and pinned SHA authenticate
        # historical bytes before the canonical Core equivalence check.
        _baseline_blobs = _bare_git.blobs(sorted({x['oid'] for x in _baseline_tree.values()}), cap_each=CAP)
        _verified_raw = {}
        for _relative, _expected_sha in sorted(_contract['core_pins'].items()):
            _git_path = _contract['core_git_paths'][_relative]
            _entry = _baseline_tree.get(_git_path)
            require(_entry is not None and _entry['oid'] == _contract['core_oids'][_relative]
                    and _entry['mode'] in ('100644', '100755') and _entry['type'] == 'blob',
                    'R1S_CP19_CORE_TREE_BINDING:' + _relative)
            _active_path = _source_root.joinpath(*_relative.split('/'))
            _active_raw = _io.read(_active_path, CAP)
            _historical_raw = _baseline_blobs[_entry['oid']]
            require(sha(_historical_raw) == _expected_sha, 'R1S_HISTORICAL_CORE_SHA:' + _relative)
            # R1R established LF-equivalence; compare actual canonical bytes
            # to independently OID/SHA-pinned historical bytes. Do not claim
            # historical raw-byte identity for CRLF-equivalent files.
            # V2 owner-authorized canonical baseline. The CP19 historical pin
            # above remains immutable. A distinct canonical SHA is required
            # only for __init__.py; all other 118 retain normalized equivalence.
            if _relative == 'mmd_registry/__init__.py':
                require(sha(_active_raw.replace(b'\r\n', b'\n')) ==
                        'cae48625419b5fe5baecdd670651bbf9bf205f24a7fc89def84f0609e2d57fee',
                        'CP23_V2_CANONICAL_INIT_NORMALIZED_SHA')
            else:
                require(_active_raw.replace(b'\r\n', b'\n') ==
                        _historical_raw.replace(b'\r\n', b'\n'),
                        'CP23_V2_CANONICAL118_NORMALIZED_MISMATCH:' + _relative)
            _verified_raw[_relative] = _active_raw
            _canonical_entry = _head_tree.get(_git_path)
            require(_canonical_entry is not None, 'R1S_CANONICAL_SOURCE_PATH_MISSING:' + _git_path)
            _canonical_raw = _io.read(_canonical.joinpath(*_git_path.split('/')), CAP)
            _head_raw = _head_blobs[_canonical_entry['oid']]
            require(_canonical_raw == _head_raw or _canonical_raw.replace(b'\r\n', b'\n') == _head_raw.replace(b'\r\n', b'\n'),
                    'R1S_CANONICAL119_SOURCE_DIRTY:' + _git_path)
        require(len(_verified_raw) == 119, 'R1S_CORE119_COUNT')
        _package = sys.modules.get('mmd_registry')
        _reader = sys.modules.get('mmd_registry.pmx.reader')
        require(type(_package) is types.ModuleType and type(_reader) is types.ModuleType
                and vars(_package).get('__version__') == '0.9.5.12', 'R1S_GENUINE_PACKAGE_VERSION')
        require(vars(_reader).get('__file__') is not None
                and Path(os.path.abspath(vars(_reader)['__file__'])) == _source_root / 'mmd_registry' / 'pmx' / 'reader.py',
                'R1S_ACTIVE_READER_LOCATION')
        # Recompile only already SHA-verified bytes. Match original function
        # code objects so mutable __file__/__spec__ labels alone cannot pass.
        # Dataclass-generated functions remain the trusted runtime lane's
        # separate responsibility; they are not source-original definitions.
        def _codes(code, result):
            for value in code.co_consts:
                if isinstance(value, types.CodeType):
                    result[value.co_qualname] = value
                    _codes(value, result)
        # marshal.dumps(code) is a strict first check but its serialized
        # reference/string encodings are not a canonical structural identity
        # certificate. Only an exact, recursive comparison of EVERY runtime
        # code field may resolve a mismatch; unknown constants fail closed.
        def _constant_diff(actual, expected, depth=0):
            if depth > 48 or type(actual) is not type(expected):
                return 'CONSTANT_TYPE_OR_DEPTH'
            if isinstance(actual, types.CodeType):
                return _code_diff(actual, expected, depth + 1)
            if actual is None or actual is Ellipsis:
                return None if actual is expected else 'CONSTANT_SINGLETON'
            if type(actual) in (bool, int, str, bytes):
                return None if actual == expected else 'CONSTANT_VALUE'
            if type(actual) is float:
                return None if struct.pack('>d', actual) == struct.pack('>d', expected) else 'CONSTANT_FLOAT_BITS'
            if type(actual) is complex:
                return None if (struct.pack('>d', actual.real) == struct.pack('>d', expected.real)
                                and struct.pack('>d', actual.imag) == struct.pack('>d', expected.imag)) else 'CONSTANT_COMPLEX_BITS'
            if type(actual) is tuple:
                if len(actual) != len(expected) or len(actual) > 65536:
                    return 'CONSTANT_TUPLE_LENGTH'
                for pos, (left, right) in enumerate(zip(actual, expected)):
                    reason = _constant_diff(left, right, depth + 1)
                    if reason is not None:
                        return 'CONSTANT_TUPLE_' + str(pos) + ':' + reason
                return None
            if type(actual) is frozenset:
                if len(actual) != len(expected) or len(actual) > 4096:
                    return 'CONSTANT_FROZENSET_LENGTH'
                # Order-independent without treating +0.0/-0.0 as equal.
                remaining = list(expected)
                for left in actual:
                    match = next((i for i, right in enumerate(remaining)
                                  if _constant_diff(left, right, depth + 1) is None), None)
                    if match is None:
                        return 'CONSTANT_FROZENSET_MEMBER'
                    remaining.pop(match)
                return None if not remaining else 'CONSTANT_FROZENSET_REMAINING'
            return 'CONSTANT_UNREVIEWED_TYPE:' + type(actual).__name__

        def _code_diff(actual, expected, depth=0):
            if depth > 48 or type(actual) is not types.CodeType or type(expected) is not types.CodeType:
                return 'CODE_TYPE_OR_DEPTH'
            # No ignored metadata: filename, first line, positions,
            # exception table and closure/local names are all compared.
            for field in ('co_argcount','co_posonlyargcount','co_kwonlyargcount',
                          'co_nlocals','co_stacksize','co_flags','co_code','co_names',
                          'co_varnames','co_filename','co_name','co_qualname',
                          'co_firstlineno','co_linetable','co_exceptiontable',
                          'co_freevars','co_cellvars'):
                left, right = getattr(actual, field), getattr(expected, field)
                if type(left) is not type(right) or left != right:
                    return 'FIELD:' + field
            return _constant_diff(actual.co_consts, expected.co_consts, depth + 1)

        # A contextlib.contextmanager decorator intentionally replaces the
        # original source function with contextlib's helper(*args, **kwargs).
        # Only the exact trusted helper, whose *sole* closure cell binds the
        # original function, is accepted; no generic __wrapped__ trust.
        _cm_helpers = tuple(value for value in contextlib.contextmanager.__code__.co_consts
                            if isinstance(value, types.CodeType)
                            and value.co_name == 'helper'
                            and value.co_qualname == 'contextmanager.<locals>.helper')
        require(len(_cm_helpers) == 1, 'R1S_CONTEXTMANAGER_HELPER_IDENTITY')
        _cm_helper = _cm_helpers[0]

        def _verified_contextmanager_original(value, module_name, module_dict):
            if type(value) is not types.FunctionType:
                return None
            wrapped = vars(value).get('__wrapped__')
            if type(wrapped) is not types.FunctionType:
                return None
            # functools.wraps copies metadata; it does not change the actual
            # stdlib helper code object, globals, defaults or closure binding.
            if value.__module__ != module_name or wrapped.__module__ != module_name:
                return None
            if value.__qualname__ != wrapped.__qualname__ or value.__name__ != wrapped.__name__:
                return None
            if value.__globals__ is not vars(contextlib) or wrapped.__globals__ is not module_dict:
                return None
            if value.__defaults__ is not None or value.__kwdefaults__ is not None:
                return None
            if _code_diff(value.__code__, _cm_helper) is not None:
                return None
            closure = value.__closure__
            if value.__code__.co_freevars != ('func',) or type(closure) is not tuple or len(closure) != 1:
                return None
            try:
                if closure[0].cell_contents is not wrapped:
                    return None
            except ValueError:
                return None
            return wrapped

        # CPython 3.12.4 dataclass-generated repr, including a pinned Core
        # base class.  A non-dataclass Core base contributes no fields; a
        # dataclass Core base contributes only source-verified inherited fields.
        # Errors are tagged, never promoted into approvals or blanket bypasses.
        _repr_rejections = []
        def _verified_dataclass_repr(value, owner, module_name, module_dict, module_ast, rejection=None):
            def deny(reason):
                if type(rejection) is list:
                    rejection.append(reason)
                return False
            if (sys.implementation.name != 'cpython' or sys.version_info[:3] != (3, 12, 4)
                    or type(owner) is not type or owner.__module__ != module_name
                    or type(value) is not types.FunctionType
                    or vars(owner).get('__repr__') is not value
                    or value.__name__ != '__repr__'
                    or value.__qualname__ != owner.__qualname__ + '.__repr__'
                    or value.__module__ != module_name or value.__globals__ is not vars(dataclasses)
                    or value.__defaults__ is not None or value.__kwdefaults__ is not None
                    or set(vars(value)) != {'__wrapped__'}
                    or not callable(getattr(dataclasses, '_repr_fn', None))):
                return deny('WRAPPER_OWNER_OR_VERSION')
            classes = [n for n in module_ast.body
                       if isinstance(n, ast.ClassDef) and n.name == owner.__name__]
            if len(classes) != 1 or owner.__qualname__ != owner.__name__:
                return deny('CLASS_AST_OR_QUALNAME')
            node = classes[0]
            if node.keywords:
                return deny('CLASS_DYNAMIC_METACLASS')
            if len(node.bases) != len(owner.__bases__) and not (not node.bases and owner.__bases__ == (object,)):
                return deny('CLASS_BASE_COUNT')
            for base_ast, base in zip(node.bases, owner.__bases__):
                if (not isinstance(base_ast, ast.Name) or base_ast.id != base.__name__
                        or type(base) is not type):
                    return deny('CLASS_BASE_AST_OR_TYPE')
                if base is object:
                    if module_dict.get(base_ast.id, object) is not object:
                        return deny('CLASS_OBJECT_BASE_BINDING')
                    continue
                # Permit only a real, source-pinned Core base loaded in the
                # already reviewed package.  No stdlib ABC, generic aliases,
                # dynamic bases, arbitrary metaclasses or multiple inheritance.
                if (len(node.bases) != 1 or not base.__module__.startswith('mmd_registry.')
                        or module_dict.get(base_ast.id) is not base
                        or base.__qualname__ != base.__name__):
                    return deny('CLASS_BASE_UNPINNED_BINDING')
                parent_module = sys.modules.get(base.__module__)
                if (type(parent_module) is not types.ModuleType
                        or vars(parent_module).get(base.__name__) is not base):
                    return deny('CLASS_BASE_MODULE_BINDING')
                if base.__module__ == module_name:
                    matches = [n for n in module_ast.body
                               if isinstance(n, ast.ClassDef) and n.name == base.__name__]
                    if len(matches) != 1:
                        return deny('CLASS_BASE_SOURCE_MISSING')
            if len(owner.__bases__) > 1:
                return deny('CLASS_MULTIPLE_INHERITANCE_UNREVIEWED')
            decorator = node.decorator_list[0] if len(node.decorator_list) == 1 else None
            if decorator is None:
                return deny('DATACLASS_DECORATOR_COUNT')
            if isinstance(decorator, ast.Call):
                if decorator.args or any(k.arg is None for k in decorator.keywords):
                    return deny('DATACLASS_DYNAMIC_OPTIONS')
                opts = {k.arg: k.value for k in decorator.keywords}
                if len(opts) != len(decorator.keywords) or any(
                        name not in ('init','repr','eq','order','unsafe_hash','frozen',
                                     'match_args','kw_only','slots','weakref_slot')
                        or not isinstance(val, ast.Constant) or type(val.value) is not bool
                        for name, val in opts.items()):
                    return deny('DATACLASS_NONLITERAL_OPTIONS')
                if 'repr' in opts and opts['repr'].value is False:
                    return deny('DATACLASS_REPR_DISABLED')
                decorator = decorator.func
            direct = isinstance(decorator, ast.Name) and decorator.id == 'dataclass' and module_dict.get('dataclass') is dataclasses.dataclass
            qualified = (isinstance(decorator, ast.Attribute) and decorator.attr == 'dataclass'
                         and isinstance(decorator.value, ast.Name)
                         and module_dict.get(decorator.value.id) is dataclasses)
            if not (direct or qualified) or not dataclasses.is_dataclass(owner):
                return deny('DATACLASS_DECORATOR_BINDING')
            if any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == '__repr__'
                   for n in node.body):
                return deny('REPR_DECLARED_EXPLICITLY')
            annotations = vars(owner).get('__annotations__')
            if (annotations is None and any(isinstance(item, ast.AnnAssign) for item in node.body)):
                return deny('CLASS_ANNOTATIONS_MISSING')
            if annotations is not None and type(annotations) is not dict:
                return deny('CLASS_ANNOTATIONS_TYPE')

            def source_fields(class_node, cls, source_dict, findings=None):
                # Source-only inspection of real fields and CPython dataclass
                # pseudo-fields.  ClassVar/InitVar/KW_ONLY are NOT repr fields.
                # They are accepted only when the AST-bound marker and the
                # corresponding runtime dataclass classification both match.
                # No evaluation of an annotation or default expression.
                def invalid(reason):
                    if type(findings) is list:
                        findings.append(reason)
                    return None
                declared, local_repr, pseudo = [], {}, {}
                seen = set()
                field_table = vars(cls).get('__dataclass_fields__')
                if type(field_table) is not dict:
                    return invalid('NO_DATACLASS_FIELD_TABLE')
                imported_typing = getattr(sys, 'modules', {}).get('typing')
                for stmt in class_node.body:
                    if not isinstance(stmt, ast.AnnAssign):
                        continue
                    if not isinstance(stmt.target, ast.Name):
                        return invalid('COMPLEX_ANNOTATION_TARGET')
                    name = stmt.target.id
                    if name in seen:
                        return invalid('DUPLICATE_ANNOTATION_NAME')
                    seen.add(name)
                    declared.append(name)
                    marker = stmt.annotation.value if isinstance(stmt.annotation, ast.Subscript) else stmt.annotation
                    marker_binding = None
                    if isinstance(marker, ast.Name):
                        marker_binding = source_dict.get(marker.id)
                    elif (isinstance(marker, ast.Attribute) and isinstance(marker.value, ast.Name)):
                        container = source_dict.get(marker.value.id)
                        if container is dataclasses and marker.attr in ('InitVar', 'KW_ONLY'):
                            marker_binding = getattr(dataclasses, marker.attr)
                        elif (container is imported_typing and imported_typing is not None
                              and marker.attr == 'ClassVar'):
                            marker_binding = getattr(imported_typing, 'ClassVar', None)
                    kind = None
                    if (imported_typing is not None and
                            marker_binding is getattr(imported_typing, 'ClassVar', None)):
                        kind = 'CLASSVAR'
                    elif marker_binding is dataclasses.InitVar:
                        kind = 'INITVAR'
                    elif marker_binding is dataclasses.KW_ONLY:
                        kind = 'KW_ONLY'
                    if kind is not None:
                        if kind == 'KW_ONLY':
                            if isinstance(stmt.annotation, ast.Subscript) or stmt.value is not None:
                                return invalid('KW_ONLY_HAS_VALUE_OR_SUBSCRIPT')
                            if name in field_table:
                                return invalid('KW_ONLY_IS_FIELD')
                        else:
                            actual = field_table.get(name)
                            expected_kind = (dataclasses._FIELD_CLASSVAR if kind == 'CLASSVAR'
                                             else dataclasses._FIELD_INITVAR)
                            if (type(actual) is not dataclasses.Field
                                    or actual._field_type is not expected_kind):
                                return invalid('PSEUDOFIELD_KIND_CHANGED:' + kind)
                        pseudo[name] = kind
                        continue
                    if (isinstance(marker, ast.Name) and marker.id in ('ClassVar','InitVar','KW_ONLY')
                            or (isinstance(marker, ast.Attribute)
                                and marker.attr in ('ClassVar','InitVar','KW_ONLY'))):
                        return invalid('PSEUDOFIELD_BINDING_NOT_VERIFIED')
                    is_repr = True
                    if isinstance(stmt.value, ast.Call):
                        callee = stmt.value.func
                        is_field = ((isinstance(callee, ast.Name) and callee.id == 'field'
                                     and source_dict.get('field') is dataclasses.field)
                                    or (isinstance(callee, ast.Attribute) and callee.attr == 'field'
                                        and isinstance(callee.value, ast.Name)
                                        and source_dict.get(callee.value.id) is dataclasses))
                        if is_field:
                            if any(k.arg is None for k in stmt.value.keywords):
                                return invalid('FIELD_DYNAMIC_KEYWORD')
                            repr_kws = [k.value for k in stmt.value.keywords if k.arg == 'repr']
                            if len(repr_kws) > 1 or (repr_kws and (not isinstance(repr_kws[0], ast.Constant)
                                                             or type(repr_kws[0].value) is not bool)):
                                return invalid('FIELD_REPR_NOT_LITERAL_BOOL')
                            if repr_kws:
                                is_repr = repr_kws[0].value
                    local_repr[name] = is_repr
                annotations = vars(cls).get('__annotations__')
                if annotations is None and not declared:
                    annotations = {}
                if type(annotations) is not dict or tuple(annotations) != tuple(declared):
                    return invalid('ANNOTATION_KEYS_DIFFER_SOURCE')
                for name, kind in pseudo.items():
                    annotation = annotations[name]
                    if type(annotation) is str:
                        annotated_node = next(s.annotation for s in class_node.body
                                              if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)
                                              and s.target.id == name)
                        if annotation != ast.unparse(annotated_node):
                            return invalid('PSEUDOFIELD_STRING_ANNOTATION_MISMATCH')
                    elif kind == 'CLASSVAR':
                        if (imported_typing is None or
                                annotation is not imported_typing.ClassVar and
                                getattr(imported_typing, 'get_origin')(annotation) is not imported_typing.ClassVar):
                            return invalid('CLASSVAR_ANNOTATION_BINDING_CHANGED')
                    elif kind == 'INITVAR':
                        if annotation is not dataclasses.InitVar and type(annotation) is not dataclasses.InitVar:
                            return invalid('INITVAR_ANNOTATION_BINDING_CHANGED')
                    elif annotation is not dataclasses.KW_ONLY:
                        return invalid('KW_ONLY_ANNOTATION_BINDING_CHANGED')
                for name in local_repr:
                    f = field_table.get(name)
                    if type(f) is not dataclasses.Field or f._field_type is not dataclasses._FIELD:
                        return invalid('LOCAL_FIELD_KIND_CHANGED')
                # An inherited dataclass may legitimately declare no new
                # fields.  Its actual effective field order is checked below.
                return local_repr

            _field_findings = []
            local_fields = source_fields(node, owner, module_dict, _field_findings)
            if local_fields is None:
                return deny('DATACLASS_LOCAL_FIELD_SOURCE:' +
                            (_field_findings[-1] if _field_findings else 'UNSPECIFIED'))
            inherited = {}
            if owner.__bases__ != (object,):
                base = owner.__bases__[0]
                if dataclasses.is_dataclass(base):
                    # Only source-verified same-module dataclass inheritance
                    # is supported, no external inherited pseudo-fields.
                    if base.__module__ != module_name:
                        return deny('DATACLASS_CROSSMODULE_PARENT_UNREVIEWED')
                    matches = [n for n in module_ast.body
                               if isinstance(n, ast.ClassDef) and n.name == base.__name__]
                    base_node = matches[0]
                    base_decs = base_node.decorator_list
                    if len(base_decs) != 1:
                        return deny('DATACLASS_PARENT_DECORATOR_COUNT')
                    dec = base_decs[0].func if isinstance(base_decs[0], ast.Call) else base_decs[0]
                    if not ((isinstance(dec, ast.Name) and dec.id == 'dataclass'
                             and module_dict.get('dataclass') is dataclasses.dataclass)
                            or (isinstance(dec, ast.Attribute) and dec.attr == 'dataclass'
                                and isinstance(dec.value, ast.Name)
                                and module_dict.get(dec.value.id) is dataclasses)):
                        return deny('DATACLASS_PARENT_DECORATOR_IDENTITY')
                    if base_node.bases or base.__bases__ != (object,):
                        return deny('DATACLASS_MULTILEVEL_PARENT_UNREVIEWED')
                    _parent_field_findings = []
                    inherited = source_fields(base_node, base, module_dict, _parent_field_findings)
                    if inherited is None:
                        deny('DATACLASS_PARENT_FIELD_SOURCE')
                        if type(rejection) is list:
                            rejection.append('DATACLASS_PARENT_FIELD_SOURCE:' +
                                             (_parent_field_findings[-1] if _parent_field_findings else 'UNSPECIFIED'))
                        return False
                    base_fields = dataclasses.fields(base)
                    if (tuple(f.name for f in base_fields) != tuple(inherited)
                            or tuple(f.name for f in base_fields if f.repr)
                                != tuple(k for k, flag in inherited.items() if flag)):
                        return deny('DATACLASS_PARENT_FIELDS_CHANGED')
            merged = dict(inherited)
            merged.update(local_fields)
            fields = dataclasses.fields(owner)
            if (tuple(f.name for f in fields) != tuple(merged)
                    or tuple(f.name for f in fields if f.repr)
                         != tuple(k for k, flag in merged.items() if flag)
                    or any(type(f) is not dataclasses.Field for f in fields)):
                return deny('DATACLASS_EFFECTIVE_FIELDS_CHANGED')
            original = vars(value)['__wrapped__']
            if (type(original) is not types.FunctionType
                    or original.__globals__ is not module_dict
                    or original.__name__ != '__repr__'
                    or original.__module__ != module_name
                    or original.__defaults__ is not None or original.__kwdefaults__ is not None):
                return deny('DATACLASS_ORIGINAL_FUNCTION_IDENTITY')
            closure = value.__closure__
            if (type(closure) is not tuple or len(closure) != 2
                    or value.__code__.co_freevars != ('repr_running','user_function')):
                return deny('DATACLASS_WRAPPER_CLOSURE_STRUCTURE')
            try:
                running, attached = (cell.cell_contents for cell in closure)
            except ValueError:
                return deny('DATACLASS_WRAPPER_EMPTY_CLOSURE')
            if type(running) is not set or running or attached is not original:
                return deny('DATACLASS_WRAPPER_CLOSURE_CONTENT')
            generated = dataclasses._repr_fn([f for f in fields if f.repr], module_dict)
            expected_original = vars(generated).get('__wrapped__')
            if (type(expected_original) is not types.FunctionType
                    or generated.__globals__ is not vars(dataclasses)
                    or expected_original.__globals__ is not module_dict
                    or _code_diff(value.__code__, generated.__code__) is not None
                    or _code_diff(original.__code__, expected_original.__code__) is not None
                    or original.__qualname__ != expected_original.__qualname__
                    or original.__annotations__ != expected_original.__annotations__
                    or value.__annotations__ != generated.__annotations__):
                return deny('DATACLASS_REGENERATED_CODE_OR_METADATA')
            return True

        for _name, _module in tuple(sys.modules.items()):
            if _name != 'mmd_registry' and not _name.startswith('mmd_registry.'):
                continue
            require(type(_module) is types.ModuleType, 'R1S_CORE_MODULE_TYPE:' + _name)
            _rel_module = _name.replace('.', '/') + '.py'
            _rel_package = _name.replace('.', '/') + '/__init__.py'
            _relative = _rel_package if _rel_package in _verified_raw else _rel_module
            require(_relative in _verified_raw, 'R1S_UNPINNED_CORE_MODULE:' + _name)
            _expected_path = _source_root.joinpath(*_relative.split('/'))
            _vars = vars(_module)
            require(isinstance(_vars.get('__file__'), str)
                    and Path(os.path.abspath(_vars['__file__'])) == _expected_path,
                    'R1S_MODULE_ORIGIN:' + _name)
            _spec = _vars.get('__spec__')
            require(_spec is not None and _spec.origin == str(_expected_path)
                    and _spec.loader is not None, 'R1S_GENUINE_MODULE_SPEC:' + _name)
            if _relative == _rel_package:
                require(list(_vars.get('__path__', [])) == [str(_expected_path.parent)],
                        'R1S_PACKAGE_PATH:' + _name)
            _original = {}
            _codes(compile(_verified_raw[_relative], str(_expected_path), 'exec', dont_inherit=True), _original)
            _module_ast = ast.parse(_verified_raw[_relative], filename=str(_expected_path))
            _actual = {}
            def _collect(values, depth=0, owner=None):
                require(depth < 16, 'R1S_CLASS_DEPTH')
                for value in values:
                    if isinstance(value, property):
                        _collect(tuple(item for item in (value.fget, value.fset, value.fdel) if item is not None), depth + 1, owner)
                        continue
                    if isinstance(value, (staticmethod, classmethod)):
                        value = value.__func__
                    if isinstance(value, types.FunctionType) and value.__module__ == _name:
                        if '__wrapped__' in vars(value):
                            original = _verified_contextmanager_original(value, _name, _vars)
                            if original is None:
                                _repr_rejections.clear()
                                _repr_ok = owner is not None and _verified_dataclass_repr(
                                    value, owner, _name, _vars, _module_ast, _repr_rejections)
                                require(_repr_ok,
                                        'R1S_UNTRUSTED_DECORATED_FUNCTION:' + _name + ':'
                                        + value.__qualname__ + ':REASON:'
                                        + (_repr_rejections[-1] if _repr_rejections else 'NO_OWNER'))
                            else:
                                _actual[value.__qualname__] = original.__code__
                        else:
                            _actual[value.__qualname__] = value.__code__
                    elif isinstance(value, type) and value.__module__ == _name:
                        _collect(tuple(vars(value).values()), depth + 1, value)
            _collect(tuple(_vars.values()))
            for _qualname, _code in _original.items():
                if '<locals>' in _qualname or _code.co_name.startswith('<'):
                    continue
                # Class bodies have CO_NEWLOCALS unset; compare actual
                # function/method definitions, not the executed class body.
                if not (_code.co_flags & 0x2):
                    continue
                require(_qualname in _actual,
                        'R1S_IN_MEMORY_CODE_MISSING:' + _name + ':' + _qualname)
                _actual_code = _actual[_qualname]
                if marshal.dumps(_actual_code) != marshal.dumps(_code):
                    _field_diff = _code_diff(_actual_code, _code)
                    require(_field_diff is None,
                            'R1S_IN_MEMORY_CODE_MISMATCH:' + _name + ':' + _qualname + ':' + str(_field_diff))
        _canonical_git.postflight()
        _bare_git.postflight()
        _io.postflight()
        return None
    except PreviewGateError:
        raise
    except Exception as _error:
        raise PreviewGateError('R1S identity could not be verified: ' + type(_error).__name__ + ':' + str(_error)[:240]) from _error


def _f(value: Any) -> float:
    num = float(value)
    if not math.isfinite(num):
        raise PreviewGateError('Non-finite geometry or material value.')
    return num


def build_projection(document: Any, source: Path, sha: str) -> dict[str, Any]:
    """Pure projection of the official parsed document into WebGL-safe arrays."""
    vertices = document.geometry.vertices
    indices = document.geometry.surface_indices
    if not 0 < len(vertices) <= MAX_VERTICES:
        raise PreviewGateError('Vertex count outside static preview limit.')
    if len(indices) % 3 or not 0 < len(indices) <= MAX_TRIANGLES * 3:
        raise PreviewGateError('Triangle count outside static preview limit.')
    if any(type(i) is not int or i < 0 or i >= len(vertices) for i in indices):
        raise PreviewGateError('Invalid surface index in source model.')
    positions: list[float] = []
    normals: list[float] = []
    uvs: list[float] = []
    bounds_min = [math.inf] * 3
    bounds_max = [-math.inf] * 3
    for v in vertices:
        if len(v.position) != 3 or len(v.normal) != 3:
            raise PreviewGateError('Invalid vertex vector dimensions.')
        for axis in range(3):
            coord = _f(v.position[axis])
            positions.append(coord)
            normals.append(_f(v.normal[axis]))
            bounds_min[axis] = min(bounds_min[axis], coord)
            bounds_max[axis] = max(bounds_max[axis], coord)
        uvs.extend([_f(v.uv[0]), _f(v.uv[1])])
    groups = []
    start = 0
    for index, mat in enumerate(document.materials):
        count = mat.surface_index_count
        if type(count) is not int or count < 0 or count % 3:
            raise PreviewGateError('Invalid material triangle partition.')
        if start + count > len(indices):
            raise PreviewGateError('Material partition exceeds triangle count.')
        color = [_f(x) for x in mat.diffuse[:3]]
        if mat.sphere_mode not in (0, 1, 2, 3):
            raise PreviewGateError('Unknown PMX sphere mode.')
        if mat.toon_reference_mode not in ('texture', 'shared'):
            raise PreviewGateError('Unknown PMX toon reference mode.')
        for ref in (mat.texture_index, mat.sphere_texture_index,
                    mat.toon_reference_index if mat.toon_reference_mode == 'texture' else -1):
            if type(ref) is not int or ref < -1 or ref >= len(document.texture_paths):
                raise PreviewGateError('Material texture reference outside document bounds.')
        if mat.toon_reference_mode == 'shared' and not (0 <= mat.toon_reference_index <= 9):
            raise PreviewGateError('Shared toon reference outside PMX range.')
        if count:
            groups.append({'start': start, 'count': count, 'color': [max(.0, min(1.0, c)) for c in color],
                           'material_index': index, 'texture_index': mat.texture_index,
                           'sphere_texture_index': mat.sphere_texture_index,
                           'sphere_mode': mat.sphere_mode,
                           'toon_reference_mode': mat.toon_reference_mode,
                           'toon_texture_index': (mat.toon_reference_index if mat.toon_reference_mode == 'texture' else -1),
                           'toon_shared_index': (mat.toon_reference_index if mat.toon_reference_mode == 'shared' else -1),
                           'ambient': [max(.0, min(1.0, _f(c))) for c in mat.ambient],
                           'specular': [max(.0, min(1.0, _f(c))) for c in mat.specular],
                           'specular_strength': max(.0, min(128.0, _f(mat.specular_strength))),
                           'drawing_flags': mat.drawing_flags,
                           'alpha': max(.0, min(1.0, _f(mat.diffuse[3])))})
        start += count
    if start != len(indices):
        raise PreviewGateError('Material partitions do not cover all triangles.')
    return {
        'status': 'ok', 'scope': 'STATIC_TEXTURE_PREVIEW_NO_SKINNING_NO_MOTION',
        'source_path': str(source), 'source_sha256': sha,
        'name': document.model_info.local_name,
        'vertex_count': len(vertices), 'triangle_count': len(indices) // 3,
        'positions': positions, 'normals': normals, 'uvs': uvs, 'indices': list(indices),
        'texture_paths': list(document.texture_paths),
        'groups': groups, 'bounds': {'min': bounds_min, 'max': bounds_max},
        'source_writes': False,
    }


def export_preview(repo: Path, source: Path) -> dict[str, Any]:
    repo = repo.resolve(strict=True)
    verify_core(repo)
    source = validate_source(source)
    initial_stat = source.stat()
    before = hash_source(source)
    # The pinned Registry reader is authoritative; never implement a second parser.
    sys.path.insert(0, str(repo))
    from mmd_registry.pmx.reader import load_pmx
    from mmd_registry import __version__
    if __version__ != '0.9.5.12':
        raise PreviewGateError('Core version mismatch.')
    result = build_projection(load_pmx(source), source, before)
    after = hash_source(source)
    final_stat = source.stat()
    if before != after or initial_stat.st_size != final_stat.st_size or initial_stat.st_mtime_ns != final_stat.st_mtime_ns:
        raise PreviewGateError('Source changed during projection; preview refused.')
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', type=Path, required=True)
    ap.add_argument('--source', type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        result = export_preview(args.repo, args.source)
        data = json.dumps(result, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
        if len(data) > MAX_PAYLOAD_BYTES:
            raise PreviewGateError('Static mesh projection exceeds 11 MB transfer bound.')
        sys.stdout.buffer.write(data)
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f'VIEWPORT_HOLD={type(exc).__name__}: {exc}', file=sys.stderr)
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
