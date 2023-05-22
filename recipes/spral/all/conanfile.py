from os import path
from conan import ConanFile
from conan.errors import ConanInvalidConfiguration
from conan.tools.apple import fix_apple_shared_install_name
from conan.tools.build import cross_building
from conan.tools.env import Environment, VirtualBuildEnv, VirtualRunEnv
from conan.tools.files import apply_conandata_patches, copy, export_conandata_patches, get, rm
from conan.tools.gnu import Autotools, AutotoolsToolchain, AutotoolsDeps, PkgConfigDeps
from conan.tools.layout import basic_layout
from conan.tools.microsoft import is_msvc, unix_path

required_conan_version = ">=1.54.0"


class PackageConan(ConanFile):
    name = "spral"
    description = "Sparse Parallel Robust Algorithm Library"
    license = "BSD-3-Clause"
    url = "https://github.com/conan-io/conan-center-index"
    homepage = "https://github.com/ralna/spral"
    topics = ("sparse linear algebra algorithms")
    package_type = "static-library"
    settings = "os", "arch", "compiler", "build_type"
    options = {
        "fPIC": [True, False],
        "with_openmp": [True, False],
        "with_cuda": [True, False],
    }
    default_options = {
        "fPIC": True,
        "with_openmp": True,
        "with_cuda": False,
    }

    @property
    def _settings_build(self):
        return getattr(self, "settings_build", self.settings)

    def export_sources(self):
        export_conandata_patches(self)

    def config_options(self):
        if self.settings.os == "Windows":
            del self.options.fPIC

        self.options["metis"].with_64bit_types = False
        self.options["openblas"].build_lapack = True

    def layout(self):
        basic_layout(self, src_folder="src")
        self.conf.define("tools.build:jobs", 1) # Fails otherwise

    def requirements(self):
        self.requires("hwloc/2.9.1")
        self.requires("metis/5.1.1")
        self.requires("openblas/0.3.23")
        if self.options.with_cuda:
            self.requires("cuda/system")  # Does not exist

    def validate(self):
        # TODO: need to check if it builds on windows (probably not)
        if self.settings.os not in ["Linux", "FreeBSD", "Macos"]:
            raise ConanInvalidConfiguration(f"{self.ref} is not supported on {self.settings.os}.")

    def build_requirements(self):
        self.tool_requires("libtool/2.4.7")
        if not self.conf.get("tools.gnu:pkg_config", check_type=str):
            self.tool_requires("pkgconf/1.9.3")
        if self._settings_build.os == "Windows":
            self.win_bash = True
            if not self.conf.get("tools.microsoft.bash:path", check_type=str):
                self.tool_requires("msys2/cci.latest")

    def source(self):
        get(self, **self.conan_data["sources"][self.version], strip_root=True)

    def generate(self):
        env = VirtualBuildEnv(self)
        env.generate()

        if not cross_building(self):
            env = VirtualRunEnv(self)
            env.generate(scope="build")
        tc = AutotoolsToolchain(self)
        yes_no = lambda v: "yes" if v else "no"
        tc.configure_args.extend([
            f"--enable-openmp={yes_no(self.options.with_openmp)}",
            f"--enable-gpu={yes_no(self.options.with_cuda)}",
            "--with-blas=yes",
            "--with-lapack=yes",
            "--with-metis=yes",
        ])
        tc.generate()
        tc = PkgConfigDeps(self)
        tc.generate()
        tc = AutotoolsDeps(self)
        tc.generate()

        # If Visual Studio is supported (?)
        if is_msvc(self):
            env = Environment()
            automake_conf = self.dependencies.build["automake"].conf_info
            compile_wrapper = unix_path(self, automake_conf.get("user.automake:compile-wrapper", check_type=str))
            ar_wrapper = unix_path(self, automake_conf.get("user.automake:lib-wrapper", check_type=str))
            env.define("CC", f"{compile_wrapper} cl -nologo")
            env.define("CXX", f"{compile_wrapper} cl -nologo")
            env.define("LD", "link -nologo")
            env.define("AR", f"{ar_wrapper} \"lib -nologo\"")
            env.define("NM", "dumpbin -symbols")
            env.define("OBJDUMP", ":")
            env.define("RANLIB", ":")
            env.define("STRIP", ":")
            env.vars(self).save_script("conanbuild_msvc")

    def build(self):
        apply_conandata_patches(self)
        autotools = Autotools(self)
        autotools.autoreconf()
        autotools.configure()
        autotools.make()

    def package(self):
        copy(self, pattern="LICENCE", src=self.source_folder,
             dst=path.join(self.package_folder, "licenses"))
        # spral_complex not installed: https://github.com/ralna/spral/issues/29
        copy(self, pattern="spral_complex.h",
             src=path.join(self.source_folder, "include"),
             dst=path.join(self.package_folder, "include"))
        autotools = Autotools(self)
        autotools.install()

        rm(self, "*.la", path.join(self.package_folder, "lib"))

        fix_apple_shared_install_name(self)

    def package_info(self):
        self.cpp_info.libs = ["spral"]

        if self.settings.os in ["Linux", "FreeBSD"]:
            self.cpp_info.system_libs.extend(["m", "pthread", "quadmath"])
