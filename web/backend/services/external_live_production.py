"""Source-pinned external issuer wiring for the approved target runtime.

No environment, application config, caller callback, or synthetic handle can
activate it. A reviewed target-specific policy must be part of a new release.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import importlib.util
import os
import re
from pathlib import Path
import stat
import sys
import time
import threading

from . import formal_admission
from .external_live_issuer import _attest_main,_LoadPermit,_FACTORY,_ENTRY,_CREDENTIAL_ID,_Sealed

if __package__=="web.backend.services":
    from ..research.external_first_answer_contract import ContractError
else:
    from research.external_first_answer_contract import ContractError


_APPROVAL=Path("/etc/structural/external-first-answer-startup.json")
_SOURCE_MANIFEST=Path("/etc/structural/external-first-answer-source.json")
_UNIT=Path("/etc/systemd/system/structural-web.service")
_RECEIPTS=Path("/var/lib/structural-isomorphism-deploy/external-first-answer-startups")
_RELEASES=Path("/srv/structural-isomorphism/releases")
_ENTRIES={}
_LIVE={}
_LIVE_LOCK=threading.RLock()
_FACTORY_LIVE=object()
_UNCERTAIN_FDS=[]


@dataclass(frozen=True,slots=True,repr=False)
class PinnedTargetPolicy:
    reviewer_public_key_hex:str
    runtime_closure_digest:str
    interpreter:str
    runtime_root:str
    dependency_files:tuple[tuple[str,str],...]


# Target-specific code-owned facts. Files or ENV cannot replace this pin.
_PINNED_POLICY=PinnedTargetPolicy(
    reviewer_public_key_hex='581ab2eb6e03b6d653c1c8a3bed1cefcb998b2f347c2b0f7474f46441bdce471',
    runtime_closure_digest='8db82891d4aa13d95de1bb6411fd65558d91447a3ff390860e36b863f08f3621',
    interpreter='/opt/structural-tools/python/cpython-3.11.15-linux-x86_64-gnu/bin/python3.11',
    runtime_root='/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5',
    dependency_files=(
        ('/opt/structural-tools/python/cpython-3.11.15-linux-x86_64-gnu/bin/python3.11', '6ec402210289b1d16bf3440775d3595e93f92e1e0ec808d4607b85f528592159'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/_cffi_backend.cpython-311-x86_64-linux-gnu.so', '192828af4429c83d5cd92c40275ffd3c71459c3dc7a58e43cf4b5c346d78dc8e'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi-2.1.1.dist-info/METADATA', '558bafb9093a8e790175d9ecff9688382981d744877dad86fd6770db0f4dc918'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi-2.1.1.dist-info/RECORD', '883cb1e8ee9b5551ffa97a90a71440e2d214ea5ae9e56beac2d93c22264cc6ac'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi-2.1.1.dist-info/WHEEL', 'b065832da3edc0b060878f3fa60d4db28f81f8eeaa767ba208f90206f288327d'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi-2.1.1.dist-info/entry_points.txt', 'a6b6108011f8e27050fe5269bba88c8051b414697880d3b0b6fbe3a03a0b001c'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi-2.1.1.dist-info/licenses/LICENSE', '5ba24ddc57067f9249add644c3afc41a5d6dc37e23433ef759d95df370b0af63'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi-2.1.1.dist-info/top_level.txt', 'ac4ed6477ad97cd2b1588f7e8e7ea1b0708097b303901f859ae41bc568c57a14'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi/__init__.py', 'c47b2db28c5f197e242d4dd4af95b7ebb0da65763fc76972cafd06f93e942cda'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi/_cffi_errors.h', '5b383ed01bb5fcad8610ad29494e5be90d86000b9d71a17cec7346f0ba05996c'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi/_cffi_gen_src.py', 'c94479de91526ec6b7b2c17bfd53aa5d368a78be402531ccfddc99f48198f6cc'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi/_cffi_include.h', 'cd8e8a168a3f6e96b4d8f6a042cd61cde5bd3b9eac9e2a25a32c6abd1280a2df'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi/_embedding.h', '3e101d00c70a0a5013559fa505c65e0c4735d85e85a9575a1ed689d8f920e84f'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi/_imp_emulation.py', '4714441bccc06c8d913c6070c3dd2eff97e2f2c59d6a1a5d8a93a83f3929ec2d'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi/_shimmed_dist_utils.py', '0638f6c26f3265bbc5bd6131e4011f9aa6aa6726458587e8c8b2d01e45d9b9aa'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi/api.py', '7165f5665b1c98ec9392fb61881a5458b712441b6a9699fe9a806ee1eb019b32'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi/backend_ctypes.py', '4fb092735e0fe6fca5a22e61ca8c7af2a841597d3bf68c075da1836d8fd4edba'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi/cffi_opcode.py', 'e7ed5c53aa691c6cecb2d17f7a88250fff2d08393bebf6619338f77d6e1289cd'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi/commontypes.py', 'ecdeb33ed08596fc57316847574f29b148dd6082b65e0b0ddf2a39760b9afefe'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi/cparser.py', '598fa8c785064ae552613b609b4d8598681b99cb9a6812b79a816591d1529ac5'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi/error.py', 'bfac53892e14d24bc3732e21fc10d1a39bf7f5942e8fe20c4582efe444dd759b'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi/ffiplatform.py', '6afc458dd8a460626812d9893bb7b0566c06fd511597a119fd668d859602aafe'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi/gen_src.py', '4d4fd9543c282e71cf95a97cfe63e6a71ab2589ed4ef9da34dcdd4b13984d502'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi/lock.py', '97d4d37703083298ba8c39091a742013d72f4c847b0809ed209afc1061edde96'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi/model.py', '700f9b10089b70751bb5ba9f80cab408b42314f02357425247333229588d805e'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi/parse_c_type.h', '39dc107f033d92dababe5081e377b11509b10c1b63d8c04d74af0b625d79b63c'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi/pkgconfig.py', 'bb2b75d7b4d079e6b77636a03355b9828f11a67c921938280b337c407c997657'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi/recompiler.py', '4c9545d3b985cd819357ab33a76ccfac977674928737e781fd2ba22621a5f4ac'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi/setuptools_ext.py', 'a59ae74ea54290632abbc37123191d6c8b65eb981e84c3f52e8ada51d4fbfb85'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi/vengine_cpy.py', 'ad1a2e610e819650085cd8d91933d45b9e2b07de76aa2de0726d7a4965d628b7'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi/vengine_gen.py', '67f2aa685eabe789f98b886341385975bfb50c14c48a69d4e32e04fcac520838'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cffi/verifier.py', 'c48cd5f220cc859d7eaa15f74515f80d6a36934ed6a5c271761840157023ae66'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography-50.0.2.dist-info/METADATA', '047cfc71226409de4318b360aef15c63a2adf609731e3dcf7fe932f14ea042ee'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography-50.0.2.dist-info/RECORD', 'eb62a1e31e3c0ed491acc2497e9e8265a810a8112122852e347e3c722757f9fd'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography-50.0.2.dist-info/WHEEL', '39b425ce6c898e83f8b8cdeeb65dae690d3ab9f2382ca9c3860e77bf6d34077a'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography-50.0.2.dist-info/licenses/LICENSE', '3e0c7c091a948b82533ba98fd7cbb40432d6f1a9acbf85f5922d2f99a93ae6bb'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography-50.0.2.dist-info/licenses/LICENSE.APACHE', 'aac73b3148f6d1d7111dbca32099f68d26c644c6813ae1e4f05f6579aa2663fe'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography-50.0.2.dist-info/licenses/LICENSE.BSD', '602c4c7482de6479dd2e9793cda275e5e63d773dacd1eca689232ab7008fb4fb'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography-50.0.2.dist-info/sboms/cryptography-rust.cyclonedx.json', '8fa299053f3da6ff2c5b85ce2b34bfc2870e2ea17c5a8629dea5b8285cd1d654'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography-50.0.2.dist-info/sboms/sbom.json', '90a9c8d03d95672422f4e7c611fb6d35d1a7c5fed98d032d9dc57d8965e239e6'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/__about__.py', '95184137751279e4ccc0ababa44ed8bc380fbcdd5ba584f0407c5d14e31c109d'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/__init__.py', '9ad86e52b4dde0544e0a9518ad322a863cfab3a4fd763019ad5ee7675a0c9b6a'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/cobblestone.py', '4fff85d3cf8051fde58daca965e92535357585639b1f9ee8a38e66552ce4f707'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/exceptions.py', 'f37e445882dcd9fc31c3e83214cae27220b64aa8558844c1d742c14b2b670c87'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/fernet.py', 'dac2c23ce99e8e13956ee75c4b742c3353c8b876f109e45c46d5a49dc437982a'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/__init__.py', 'e48c2b2d6ad5a7402312bff815d586fd5d39ecd489198fd6e1e80d36cb9cb748'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/_oid.py', '3a17b69d413a5e32b1d5417a4c0b06532daff06509f958bd0d2e32c52ba4b795'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/asn1/__init__.py', '62a613a071858cb38a8a0442d341c68fa86b8c4c1bbb548fa408aeebebbe7daa'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/asn1/asn1.py', 'f6671fae676f2bb2ad8e1458a1f3330235b4bbb9efa9b7ecbcf7db84d40ad414'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/backends/__init__.py', '3b98ef28541d6675e129ea89f87b6e95a10bf4d8bb9abd660f3658e641e56212'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/backends/openssl/__init__.py', 'a778e625f9c26a0f62139b1d32b37a56f544bb9e6ee3ac5a4bf223a08d12ae60'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/backends/openssl/backend.py', 'd0d73315b8b01b17eaf6a8b6f281d8af4f2bfebed5420e005c78dbd2814fc2a0'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/__init__.py', 'c0709b59f69e7daf9f93a4c74b0f6d87d7c952c4ad268ef6e39c1f141aa676e0'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust.abi3.so', '1e5d23fa66915204b9b67202a46993844d81cda56f6ad52cead2def37617ee29'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/__init__.pyi', 'b949e7bceabfb9a99e62704da66b2fdd244054ed16406a63239f1a47594be0ac'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/_openssl.pyi', '4ffe53a583bc6e08483e3010dc1b40001ab0f82718b241e9f76c26e4f358e9d7'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/asn1.pyi', '06b1a30bc27a9f0b92fabdc455c757241f27768b5f63d99b41839fa5b3c6d070'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/cobblestone.pyi', 'f6551fd56d614ebb33109e18a527093483d20fd04e33ba3e0bcdbe9ad4831bda'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/declarative_asn1.pyi', '30198e6732d37663c9ebed4ae80ab73d3b872753068117c8bb484881a83ba1c1'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/exceptions.pyi', '7b15ebdb1c3fd29075924f777186ccdcca216f3a149233a6b3564c522d2e4191'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/ocsp.pyi', '54f556b8a1c8f4432cd3d64b458006bd1d08cf49823261335c0920247a2fa683'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/openssl/__init__.pyi', '3ba18ecaf0f1b7aca589c0766851aebb945c199cbd5232a762a191f2bab3bddc'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/openssl/aead.pyi', 'eddfbec5d734beecd17b84b6bae41a1a6fbd1862afe0d7122d070bc9671a0fab'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/openssl/ciphers.pyi', '2e13f31d649726ae20ac02579facd2bd249d57e698208b1c1c3c083e524618fb'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/openssl/cmac.pyi', '9cf1f45f9ed1629b00911a305698d0887139eba4e1513c7b617aec69d9ab9879'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/openssl/dh.pyi', '6774c2f86d38f931ed49d00e3cb3358761bb9a5e5b75ad4495951c9f9c29ba19'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/openssl/dsa.pyi', 'a81b64823d9a95bb76a8572767d503ae1ce83610953bb1d36f2e5549fd445cc2'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/openssl/ec.pyi', 'cc9cb4a516b99fefe9d9d9b8e4fc44081ffe07a49567234a7e3c450e93ea4f7f'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/openssl/ed25519.pyi', '5577d77791ba8548af837f7d4750d87665b77936f411e6f30d3aa3442da0691c'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/openssl/ed448.pyi', '631e3d96a7678ec0fb6f188357591c68cac392dba0e5ebe2e5aeb37ab322cb6b'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/openssl/hashes.pyi', '6c57b74f5dd47b24489d424c0fe47902b19318ba960e25a8d8bbf6286cd46dfe'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/openssl/hmac.pyi', '057667ecd0e32f72406d85b4490f298358b20b90db4175615008b0b22f03151f'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/openssl/hpke.pyi', 'a7f8462e7e981fe11aac91755796d4b14b638a9be2100a5c4793b4b141c92ed7'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/openssl/kdf.pyi', '1e288b74407d9ea32c4ef330885a694297cfcfa7c7533f7f8298c407f5c03970'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/openssl/keys.pyi', 'b5e22df0ce9910c26b9f8b375b45275b40d9fb7d0977af169d2b0a286d76e25d'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/openssl/keywrap.pyi', '9860891284389718b8091393044b94cdbf54e24cbc9f9d8bde20ef08e5cd0512'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/openssl/mldsa.pyi', '1fce170d6d134372c785d1890f9b8f6834f98a31222ba319cad5d873cac135fe'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/openssl/mlkem.pyi', '6f2a1ebace3e9483a55a5122450742734d2a0a45e9381e6978163aca8f6293cb'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/openssl/poly1305.pyi', 'fd25bd36d4391439406dd72516d5a94f89469b1288287a4dfb88fc27607361f4'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/openssl/rsa.pyi', 'd8e4023525e4c6073edeec35c620829682104d5ea9f7f90aefd62ed2b85980f7'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/openssl/x25519.pyi', '7b09f81a94326fbccfc04fa78bb1adc9080c0b403598bbaa62c4b2aafea723fb'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/openssl/x448.pyi', '8ee4d94e6962f233bfe5572e7e0faf1efc7fb42c9ece648b221ffd3d4dd37332'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/pkcs12.pyi', 'bc411de700e266f6fc64615ace22c26962f3030a06fedbcf5312d0c39fee3a5f'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/pkcs7.pyi', 'b711812628ea66c84472aadae9bc8f35b9e2b08765c733922073f6865f5aacfb'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/test_support.pyi', '3cf86577e5a43bbe3789714f79b786d0bb602b4693cc6763708b1acb51a6e461'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/_rust/x509.pyi', '2d54f886d04db1ee608a3421e0685535811b00ed04d40360136f2d5aac378382'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/openssl/__init__.py', 'c0709b59f69e7daf9f93a4c74b0f6d87d7c952c4ad268ef6e39c1f141aa676e0'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/openssl/_conditional.py', 'bdfce2fb11dd4ad01c2508cbaaa3a54a8b3de0bf03feda85b417bb3afc3e2ad6'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/bindings/openssl/binding.py', '16cb8bc5b4e7aea5bad3e7405ad6a482e7deabb4e7a9a41a8b53dcec3a30ae3a'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/decrepit/__init__.py', 'c0709b59f69e7daf9f93a4c74b0f6d87d7c952c4ad268ef6e39c1f141aa676e0'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/decrepit/ciphers/__init__.py', 'c0709b59f69e7daf9f93a4c74b0f6d87d7c952c4ad268ef6e39c1f141aa676e0'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/decrepit/ciphers/algorithms.py', '5923e3336b177eb2c35ebb4de51ecdeab0355c5edbf772357bf96f0f8cb1da80'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/decrepit/ciphers/modes.py', '3aafcf1300a47b938b73339faffbf300e27ac0fc7eae5b2f1c05cf06e8796fda'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/__init__.py', 'c0709b59f69e7daf9f93a4c74b0f6d87d7c952c4ad268ef6e39c1f141aa676e0'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/_asymmetric.py', '46181ca2e501e874e214306b4752f1aa4323a54c4888dbd0d6bff3263446eaa4'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/_cipheralgorithm.py', '121de2ee5c1e7477e2d1e2d2b07f773d9c502b363d23a9642baeef2f8579b4e7'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/_modes.py', 'fc4880383f096fa5a915796ec247144f7102cff4c7f318c6bdb4251a4366e7d4'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/_serialization.py', '862d3125b941019f29999c769566be96bba9871befbc6de0f4334ad06f0e75fb'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/asymmetric/__init__.py', 'c0709b59f69e7daf9f93a4c74b0f6d87d7c952c4ad268ef6e39c1f141aa676e0'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/asymmetric/dh.py', '467b767cb683a501234125fc7cdb659935ce2478e5b7f0ca419d5595f85d8dae'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/asymmetric/dsa.py', '910cd3562a8023d3e210b34e05ca3f9fa31f3f737d7a120f91276e3a9ba9b743'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/asymmetric/ec.py', '2e495508b2f16db433aa213a1d16984d16ae2cca61614c37b44e9cf28048c584'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/asymmetric/ed25519.py', '99b7df2efb3edcf8020de835ad05d55e1ec62e7b6554be004e390811ce29b793'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/asymmetric/ed448.py', '9f474aeb2f952f1bb0fb3beb0f1b8f4f8e7df21ca6817fb5472fe3abd6944211'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/asymmetric/mldsa.py', '2c731a694d26eba12c4ab4a87567f87b691d99d0d14c41910b5cbe7c22b118ad'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/asymmetric/mlkem.py', 'c2f5647854fee287fe55c500111dbecc8ff98574faaf04c93cc090f2017d1930'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/asymmetric/padding.py', '8db81a8ef18763090f8cc0e58c7bb99713019437e60b15947b6005d92e8a135d'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/asymmetric/rsa.py', '94813b9467b8e3d5b95112d3282a6f1467ab213a2e2a8655f46c2e4f349cb12a'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/asymmetric/types.py', '4a32614eb9c544b9533dd62b043d69a0c8ba723606f9f8747d221a427dd0522c'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/asymmetric/utils.py', '42cf117bd1853e35bfb4da7fef721e2448cf09fd2c94e22c58ec68eaaca64fa9'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/asymmetric/x25519.py', '950720524f8f8ae6e3f329c535641e6267b7b5864c80742a9112a42033872f3a'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/asymmetric/x448.py', '6f7ee283b93ba681ba4890ebcb8da3f849428f9ab8790d17e421663744a7f33f'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/ciphers/__init__.py', '7b21179a393afc265768e3d80ebeef018197af6f50bf38162f6fb8092a252c5b'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/ciphers/aead.py', '173972c7bc3c29841a9330e9d735a026722beb6ce066b815875bb68787b1079e'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/ciphers/algorithms.py', '2067c2c9c6093a1d53be8237e2b7f0f0a7c9ff19add69fc3a4186dd8582171ea'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/ciphers/base.py', '6810bb1c7041a22c5e6e6a5aad5af4525383b37543d00ec1ea8cff01a4630eff'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/ciphers/modes.py', '1fb0194a02624930428b482b2fdecdc5a912f79d09c852982ecadaf2d8c73f14'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/cmac.py', 'b33fece87fdc6273afc7e54d59d20a85185edd89a9f33f09d03dc206a397de08'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/constant_time.py', 'c5dba7593d277fc3af29d72a52186514a6b21a9e3f3e0549454d96d702d2aff0'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/hashes.py', '4abb7081cdffa45bd97c88518fd7b5a7859d8be17f3e995e18796a240460b4e8'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/hmac.py', '469077cfdcf9b248ab090ae6ef341bb67a7da4b327023ae54d4bcaa85e5a0c37'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/hpke.py', '46c1e2b2c0b997e7533e7d69d896dcac8ac09c306b2ea339ba0045486a662aee'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/kdf/__init__.py', 'bf7ca2601194dbbd84a233576f07d865d6db7c8f5c54e0821b79d78530dd6b79'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/kdf/argon2.py', '649c7e7a7525000e28edbe3a0b5c25cc6fd7010416d3022416050a92b33fc00f'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/kdf/concatkdf.py', '0459ce292ef6b71285d3242f012af435aeee873bcb1e95027242b988d002fda4'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/kdf/hkdf.py', '33494011f468738929a78fa7c038fdc81faf359ba420e60442b5255ac04d9fda'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/kdf/kbkdf.py', '0b7c3df6f8c5aa1ab3031cc5387e33cef5681e46f9002e8bcfa00440657b77f8'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/kdf/pbkdf2.py', '5dc86493df6cf8c93a6fa2920a8baa764f0557288d54e48521e9e69d6ded2e04'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/kdf/scrypt.py', '5f259475452686e23d57a4ea00f3afba3092306bf55d0760d1adb52160a63be5'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/kdf/x963kdf.py', '40a8e145e86e4ec02cb4bdfce1b29fbe3bafd727dd6a6007561b014567a7d95c'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/keywrap.py', 'b7db7c299bb367852cdf4012521236ecc64f3cf2b2e041114439002be94ced34'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/padding.py', '413f94f8dbd5d9e4063b5c153db0e234635273d91e4434be8a0e5c40eacbcf41'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/poly1305.py', '3f910f415f9107f1493da869834d6ed13b384bf3e7026b2ba312065db19e451a'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/serialization/__init__.py', '7d772ee3dba02fdaf1869465ff06639cca84f430a484231cb11c5f8ffa93bde8'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/serialization/base.py', '48006bbe8d12f3a41ca01963ec3a6378b5b2da5cd032bca28a827a0eb1184150'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/serialization/pkcs12.py', '992f5c14d1b869fcefb1ea1ce5ed4c5a863656c91f2fc37c63f3858e5ebb96e6'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/serialization/pkcs7.py', '98533b385b99f1c0b1506528a380a87fa06708773f21bc750108e37f19cf971a'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/serialization/ssh.py', '162b177bf9d429d3c67ea10d5612a99a86b399a23ca87f067be5466dcd1dca4c'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/twofactor/__init__.py', 'b66319181fa0e08535afb94816a012534d7dcebd2e3e9ff010161cc1d0c22820'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/twofactor/hotp.py', '8af668e41adc08658bb2aaa5e27655d175c28f218f8bf8877c3165b4694e2709'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/hazmat/primitives/twofactor/totp.py', '9b92cfa512f4d24a78cd8f204e3af9e477f3f5a3253d2e7790799591240299d6'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/py.typed', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/utils.py', '21aed2d106734b47b3c2920741f63c1b57bea381a3ac78a31175e3c00af58ae2'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/x509/__init__.py', 'd0a54d4e646d758357fe2fdec2c4cdcdb4e6d9ed6ac9fa0e85ce1e9a883984be'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/x509/base.py', '50830a9309acc75d01477fe09c14410814f0429d7e3bcc247d59bb6b31fefe61'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/x509/certificate_transparency.py', '26aa0e203865c089eb60c156e88167efb589d2f885f8f07fae5655defb3d3187'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/x509/extensions.py', 'fa25dcc169c82f5ce5e4c977055245904a3fef59dc5def387a1beacd6d6c2b83'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/x509/general_name.py', 'b0ffeb575d50969b24e31dd75c6258fccbf443fb3d76d8de2dc907b23a4b4284'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/x509/name.py', 'a08db0e95758f33830eeaa4d865c44c79d765b40215835d0ac361fe44b0cd8f6'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/x509/ocsp.py', '61ecba35d155d4c3e3a29db8323fd57a78c4a60de451a328a5258e2b401b781b'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/x509/oid.py', '054ce05d71955a296406474a3d39bd478a84944f600061e07583cc640a7b3c9a'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/cryptography/x509/verification.py', '811d82d9cf97650b5b959853e53e6f8d228eb426fbe1e7f66a53d59847301653'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/pycparser-3.12.dist-info/METADATA', 'ad8db5fe2b0e0a3b0e8419fe5041b80be92470a40b06bd9c1462a0a8bb637c92'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/pycparser-3.12.dist-info/RECORD', 'b2a227ea2913449fb429db4f6a20a8e83175759641c97913759b2b3f4417727f'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/pycparser-3.12.dist-info/WHEEL', '98e75747d0b7c0c568bfb71263c3d8f970b3a374a6996087bc642be5cb09a1aa'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/pycparser-3.12.dist-info/licenses/LICENSE', '0a9e78156ae8b96caf1b4f11ac2df424b83de29736f9e757630548a6272fdf90'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/pycparser-3.12.dist-info/top_level.txt', '73e94f712ef82fff0aa07ec813a3d0179a1fca2ad140d57856191b48520f7963'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/pycparser/__init__.py', '35922781317a3f15be51e6676d8fc2c6690f1b9c8f108d5705fff94835e34a14'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/pycparser/_ast_gen.py', '3ca193689f1e47f2be2856b2bc969642672fd54820dfdf8749cf37364bfb786b'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/pycparser/_c_ast.cfg', '47d94972e972397535e778a44f220a6c215ef137e4dbe7220adc9ff72a660798'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/pycparser/ast_transforms.py', 'cbc35d509a8b833cb00732666c92ef6dcb0d46d2b3da0dd87ea42f8062fecf58'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/pycparser/c_ast.py', '042a060231e60d1f12d1dd061ab114384e0d506605651b7e5bd6e9d257781896'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/pycparser/c_generator.py', '770c62a48e69a505cc374ce3f39d4eb6a21610affe72d45067f2059d838ac882'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/pycparser/c_lexer.py', 'ef5e16cc8031c4880672978d0080b59e9bd94a5b2cd66e16c0b52cf1dfbe105e'),
        ('/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a5/lib/python3.11/site-packages/pycparser/c_parser.py', 'b8c9a31bc8e57a075de2c44821995ba339653fa19d29e2dfbe2ea864a7381e48'),
    ),
)


def _fixed_file(path,limit):
    if not path.is_absolute() or path.resolve(strict=True)!=path:
        raise ContractError("external_startup_material_path")
    for parent in path.parents:
        info=parent.stat(follow_symlinks=False)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:
            raise ContractError("external_startup_material_path")
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_uid!=0 or before.st_nlink!=1 or before.st_mode&0o022 or before.st_size>limit:
            raise ContractError("external_startup_material_file")
        with os.fdopen(fd,"rb",closefd=False) as stream:
            raw=stream.read(limit+1)
        actual=os.fstat(fd);named=path.stat(follow_symlinks=False)
        key=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if len(raw)!=before.st_size or key(before)!=key(actual) or key(before)!=key(named):
            raise ContractError("external_startup_material_changed")
        return raw
    finally:os.close(fd)


def _verify_runtime_files(policy,expected_digest):
    root=Path(policy.runtime_root)
    interpreter=Path(policy.interpreter)
    if (sys.platform!="linux" or Path(sys.executable).resolve(strict=True)!=interpreter
            or not root.is_absolute() or root.resolve(strict=True)!=root or not policy.dependency_files
            or len(policy.dependency_files)>4096):
        raise ContractError("external_runtime_closure_unbound")
    seen=set()
    checks=[]
    for name,sha in policy.dependency_files:
        path=Path(name)
        if name in seen or (path!=interpreter and not path.is_relative_to(root)):
            raise ContractError("external_runtime_closure_unbound")
        seen.add(name)
        if hashlib.sha256(_fixed_file(path,64*1024**2)).hexdigest()!=sha:
            raise ContractError("external_runtime_closure_changed")
        checks.append((name,sha))
    # Only import cryptography after checking its actual installed closure.
    if interpreter.as_posix() not in seen or any(k=="cryptography" or k.startswith("cryptography.") for k in sys.modules):
        raise ContractError("external_runtime_closure_unbound")
    for name in ("cryptography","cffi","_cffi_backend","pycparser"):
        spec=importlib.util.find_spec(name)
        if spec is None or spec.origin not in seen:
            raise ContractError("external_runtime_closure_unbound")
    import json
    raw=json.dumps(sorted(checks),separators=(",",":"),ensure_ascii=False).encode()
    if hashlib.sha256(raw).hexdigest()!=expected_digest:
        raise ContractError("external_runtime_closure_changed")


def publish_entry_for_serve(app,witness):
    """Borrow the existing hardened directory witness, not its old grant."""
    if _PINNED_POLICY is None:
        return
    from . import native_live_credentials
    native_live_credentials._entry_caller("_serve")
    if type(witness) is not native_live_credentials.EntryCredentialDirectoryWitness or id(app) in _ENTRIES:
        raise ContractError("external_entry_witness_required")
    witness.require_runtime()
    _ENTRIES[id(app)]=(app,witness)


def unpublish_entry_for_serve(app):
    if _PINNED_POLICY is None:return
    from . import native_live_credentials
    native_live_credentials._entry_caller("_serve")
    _ENTRIES.pop(id(app),None)


@contextmanager
def _receipt_directory(expected):
    if _RECEIPTS.resolve(strict=True)!=_RECEIPTS:
        raise ContractError("external_startup_receipt_unbound")
    for parent in _RECEIPTS.parents:
        s=parent.stat(follow_symlinks=False)
        if not stat.S_ISDIR(s.st_mode) or s.st_uid!=0 or s.st_mode&0o022:
            raise ContractError("external_startup_receipt_unbound")
    parent=os.open(_RECEIPTS,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        s=os.fstat(parent)
        if ((s.st_dev,s.st_ino,s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode))!=
                (expected.receipts_dev,expected.receipts_ino,expected.runtime_uid,expected.runtime_gid,0o700)):
            raise ContractError("external_startup_receipt_unbound")
        yield parent
    finally:os.close(parent)


def _consume(expected,receipt):
    with _receipt_directory(expected) as parent:
        name="spent-"+receipt.startup_id+".json"
        try:fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=parent)
        except FileExistsError:raise ContractError("startup_challenge_already_consumed") from None
        import json
        with os.fdopen(fd,"wb") as stream:
            stream.write(json.dumps({"startup_id":receipt.startup_id,"approval_digest":receipt.approval_digest,
                                     "source_commit":receipt.source_commit,"no_auto_retry":True},
                                    sort_keys=True,separators=(",",":")).encode())
            stream.flush();os.fsync(stream.fileno())
        os.fsync(parent)



_P1_SPENT="spent-p1-operation"


def _p1_spent_at(parent):
    try:os.stat(_P1_SPENT,dir_fd=parent,follow_symlinks=False)
    except FileNotFoundError:return False
    # Any existing object at this name is spent, including an incomplete
    # record after an uncertain fsync. Never repair or unlink to reopen.
    return True


def _claim_p1_at(parent,operation_key):
    if type(operation_key) is not str or not re.fullmatch(
            r"[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}",operation_key):
        raise ContractError("external_canary_binding_changed")
    opaque=hashlib.sha256(b"structure-external-first-answer-p1-operation-v1\0"+operation_key.encode("ascii")).hexdigest()
    try:
        fd=os.open(_P1_SPENT,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=parent)
    except FileExistsError:
        raise ContractError("external_canary_already_spent") from None
    with os.fdopen(fd,"wb") as stream:
        stream.write((opaque+"\n").encode("ascii"))
        stream.flush();os.fsync(stream.fileno())
    os.fsync(parent)


def p1_already_spent(app,handle):
    if type(handle) is not _LiveHandle:
        raise ContractError("real_external_live_handle_required")
    handle.require_for_sender(app)
    try:
        with _receipt_directory(handle._expected) as parent:return _p1_spent_at(parent)
    except OSError:raise ContractError("external_startup_receipt_unbound") from None


def claim_p1_before_first_write(app,handle,operation_key):
    from .external_live_sender import _Ticket,_require_live
    frame=sys._getframe(1)
    try:
        if frame.f_code is not _Ticket.first_write.__code__ or type(handle) is not _LiveHandle:
            raise ContractError("external_consumption_ticket_required")
    finally:del frame
    policy,_=_require_live(handle,app)
    if policy.canary_operation_key!=operation_key:
        raise ContractError("external_canary_binding_changed")
    try:
        with _receipt_directory(handle._expected) as parent:_claim_p1_at(parent,operation_key)
    except OSError:raise ContractError("external_startup_receipt_unbound") from None


def _saved_operation_name(operation_key):
    if type(operation_key) is not str or re.fullmatch(r"[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}",operation_key) is None:
        raise ContractError("external_operation_binding_changed")
    opaque=hashlib.sha256(b"structure-external-first-answer-saved-question-operation-v1\0"+operation_key.encode("ascii")).hexdigest()
    return "spent-operation-"+opaque


def _saved_operation_spent_at(parent,operation_key):
    try:os.stat(_saved_operation_name(operation_key),dir_fd=parent,follow_symlinks=False)
    except FileNotFoundError:return False
    return True


def _claim_saved_operation_at(parent,operation_key):
    name=_saved_operation_name(operation_key)
    try:fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=parent)
    except FileExistsError:raise ContractError("external_operation_already_spent") from None
    with os.fdopen(fd,"wb") as stream:
        # Only a nonprivate random operation digest persists after erasure.
        stream.write((name.removeprefix("spent-operation-")+"\n").encode("ascii"))
        stream.flush();os.fsync(stream.fileno())
    os.fsync(parent)


def operation_already_spent(app,handle,operation_key):
    from .external_live_sender import _require_live,_valid_operation_key
    policy,_=_require_live(handle,app)
    if not _valid_operation_key(operation_key) or (policy.request_mode=="canary" and operation_key!=policy.canary_operation_key):
        raise ContractError("external_operation_binding_changed")
    if policy.request_mode=="canary":return p1_already_spent(app,handle)
    try:
        with _receipt_directory(handle._expected) as parent:return _saved_operation_spent_at(parent,operation_key)
    except OSError:raise ContractError("external_startup_receipt_unbound") from None


def claim_saved_question_before_first_write(app,handle,operation_key):
    from .external_live_sender import _Ticket,_require_live,_valid_operation_key
    frame=sys._getframe(1)
    try:
        ticket=frame.f_locals.get("self")
        if (frame.f_code is not _Ticket.first_write.__code__ or frame.f_globals is not _Ticket.first_write.__globals__
                or type(handle) is not _LiveHandle or type(ticket) is not _Ticket
                or ticket.writer.handle is not handle or ticket.writer.app is not app
                or ticket.run!=operation_key or ticket.writer.key!=operation_key):
            raise ContractError("external_consumption_ticket_required")
    finally:del frame
    policy,_=_require_live(handle,app)
    if policy.request_mode!="saved-question" or not _valid_operation_key(operation_key):
        raise ContractError("external_operation_binding_changed")
    try:
        with _receipt_directory(handle._expected) as parent:_claim_saved_operation_at(parent,operation_key)
    except OSError:raise ContractError("external_startup_receipt_unbound") from None


class _LiveCredential(_Sealed):
    __slots__=("_raw","_active")
    def __init__(self,raw,*,factory):
        if factory is not _FACTORY_LIVE or type(raw) is not bytearray:
            raise PermissionError("external credential factory required")
        object.__setattr__(self,"_raw",raw)
        object.__setattr__(self,"_active",True)
    def retire(self):
        for index in range(len(self._raw)):self._raw[index]=0
        self._raw.clear()
        object.__setattr__(self,"_active",False)


def _load_credential(permit,witness):
    from . import native_live_credentials as entry
    permit.claim(witness,entry=_ENTRY,credential_id=_CREDENTIAL_ID)
    witness.require_runtime()
    module=entry._formal_metadata_entry()
    helper=module._require_metadata_helper()
    directory=witness.fds[-1]
    root_snapshot=module._capture_metadata(directory)
    root_shape=helper.validate_snapshot(root_snapshot,"directory",witness.uid,os.getegid())
    fd=os.open(_CREDENTIAL_ID,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=directory)
    value=None
    try:
        before,shape=module._metadata_pair(directory,_CREDENTIAL_ID,fd,witness.uid,"file")
        if shape!=root_shape or before["mount_id"]!=root_snapshot["mount_id"] or not 1<=before["size"]<=4096:
            raise ContractError("external_credential_metadata_rejected")
        raw=os.read(fd,4097)
        os.lseek(fd,0,os.SEEK_SET)
        again=os.read(fd,4097)
        after,_=module._metadata_pair(directory,_CREDENTIAL_ID,fd,witness.uid,"file")
        witness.require_runtime()
        if not helper.same_snapshot(before,after) or len(raw)!=before["size"] or raw!=again:
            raise ContractError("external_credential_changed")
        entry.validate_provider_bytes(raw)
        value=_LiveCredential(bytearray(raw),factory=_FACTORY_LIVE)
    finally:
        try:os.close(fd)
        except OSError:
            if value is not None:value.retire()
            _UNCERTAIN_FDS.append(fd)
            raise RuntimeError("external credential retirement uncertain") from None
    return value


class _LiveHandle(_Sealed):
    __slots__=("_app","_binding","_expected","_resource","_entry")
    def __init__(self,app,binding,expected,resource,witness,*,factory):
        if factory is not _FACTORY_LIVE or type(resource) is not _LiveCredential:
            raise PermissionError("external live handle factory required")
        for name,value in (("_app",app),("_binding",binding),("_expected",expected),("_resource",resource),("_entry",witness)):
            object.__setattr__(self,name,value)
    def __repr__(self):return "<sealed external live credential handle>"
    def require_for_sender(self,app):
        if self._app is not app or _LIVE.get(id(app)) is not self or not self._resource._active or _attest_main(app,self._expected) is not self._binding:
            raise ContractError("external_live_handle_retired")
        self._entry.require_runtime()
        # No API exposes raw bytes. A later independently bound sender can
        # require this exact handle at reservation/consume.


def _prepare(app):
    if type(_PINNED_POLICY) is not PinnedTargetPolicy or id(app) in _LIVE:
        raise ContractError("external_production_policy_unbound")
    entry=_ENTRIES.get(id(app))
    if entry is None or entry[0] is not app:
        raise ContractError("external_entry_witness_required")
    witness=entry[1]
    witness.require_runtime()
    if (Path(__file__).resolve().parents[3].parent!=_RELEASES or sys.platform!="linux"
            or (os.geteuid(),os.getegid())!=(981,976)):
        raise ContractError("external_production_target_unbound")
    # Hash-check the code-owned target dependency closure before importing
    # cryptography. The signed Go is issued after the source is finalized;
    # its source SHA is not a self-referential constant in this file.
    _verify_runtime_files(_PINNED_POLICY,_PINNED_POLICY.runtime_closure_digest)
    from research.external_first_answer_issuer_contract import SignedApproval,_verify
    from research.provider_schemas import strict_json
    approved_bytes=_fixed_file(_APPROVAL,16384)
    expected=SignedApproval.model_validate(strict_json(approved_bytes,cap=16384)).approval.binding
    receipt=_verify(approved_bytes,expected,bytes.fromhex(_PINNED_POLICY.reviewer_public_key_hex),int(time.time()))
    root=Path(__file__).resolve().parents[3]
    if root.name!=expected.source_commit or expected.runtime_closure_digest!=_PINNED_POLICY.runtime_closure_digest:
        raise ContractError("external_source_changed")
    raw_source=_fixed_file(_SOURCE_MANIFEST,2*1024**2)
    if hashlib.sha256(raw_source).hexdigest()!=expected.source_manifest_digest:
        raise ContractError("external_source_changed")
    source=strict_json(raw_source,cap=2*1024**2)
    if source.get("schema")!="formal-main-source-payload-v1" or source.get("source_sha")!=expected.source_commit:
        raise ContractError("external_source_changed")
    paths={row["path"]:row["sha256"] for row in source["members"]}
    if len(paths)!=len(source["members"]):
        raise ContractError("external_source_changed")
    for name in ("scripts/run-formal-main.py","web/backend/main.py",
                 "web/backend/services/external_live_issuer.py","web/backend/services/external_live_production.py",
                 "web/backend/services/external_live_sender.py","web/backend/services/external_live_operations.py",
                 "web/backend/research/external_first_answer_issuer_contract.py"):
        if hashlib.sha256(_fixed_file(root/name,512*1024)).hexdigest()!=paths.get(name):
            raise ContractError("external_source_changed")
    dropins=("service.d","structural-.service.d","structural-web.service.d")
    unit_roots=(Path("/etc/systemd/system"),Path("/run/systemd/system"),
                Path("/usr/local/lib/systemd/system"),Path("/usr/lib/systemd/system"),Path("/lib/systemd/system"))
    if (hashlib.sha256(_fixed_file(_UNIT,16384)).hexdigest()!=expected.unit_digest
            or any(os.path.lexists(directory/name) for directory in unit_roots for name in dropins)
            or Path("/proc/self/cgroup").read_text().splitlines()!=["0::/system.slice/structural-web.service"]):
        raise ContractError("external_unit_changed")
    binding=_attest_main(app,expected)
    return binding,witness,expected,receipt


def activate(app):
    if _PINNED_POLICY is None:return None
    caller=sys._getframe(1)
    try:
        main=sys.modules.get("main")
        if main is None or caller.f_code is not main.lifespan.__wrapped__.__code__ or caller.f_locals.get("app") is not app:
            raise ContractError("external_main_startup_required")
    finally:del caller
    try:
        binding,witness,expected,receipt=_prepare(app)
        _consume(expected,receipt)
    except (ContractError,OSError,ValueError,TypeError,KeyError,RuntimeError,ImportError):
        # No loader has run. A possibly written challenge stays spent.
        return None
    permit=_LoadPermit(binding,_load_credential,witness,factory=_FACTORY)
    resource=None
    try:
        resource=_load_credential(permit,witness)
        if not permit._used or _attest_main(app,expected) is not binding:
            raise ContractError("external_main_attestation_rejected")
        handle=_LiveHandle(app,binding,expected,resource,witness,factory=_FACTORY_LIVE)
        with _LIVE_LOCK:_LIVE[id(app)]=handle
        return handle
    except (ContractError,OSError,ValueError,PermissionError):
        if resource is not None:resource.retire()
        return None
    except BaseException:
        if resource is not None:resource.retire()
        raise
    finally:object.__setattr__(permit,"_active",False)


@contextmanager
def wire_latch():
    """First write and resource retirement share one process-local lifetime latch."""
    with _LIVE_LOCK:yield


def retire(app,handle):
    with wire_latch():
        if handle is not None:
            if type(handle) is not _LiveHandle or _LIVE.get(id(app)) is not handle:
                raise ContractError("external_live_handle_retired")
            _LIVE.pop(id(app))
            handle._resource.retire()
