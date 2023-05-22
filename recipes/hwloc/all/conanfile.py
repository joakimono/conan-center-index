from conan import ConanFile
from conan.errors import ConanInvalidConfiguration
from conan.tools.apple import fix_apple_shared_install_name
from conan.tools.build import check_min_cppstd, cross_building
from conan.tools.env import Environment, VirtualBuildEnv, VirtualRunEnv
from conan.tools.files import apply_conandata_patches, copy, export_conandata_patches, get, rm, rmdir
from conan.tools.gnu import Autotools, AutotoolsToolchain, AutotoolsDeps, PkgConfigDeps
from conan.tools.layout import basic_layout
from conan.tools.microsoft import is_msvc, unix_path
import os

required_conan_version = ">=1.54.0"


class PackageConan(ConanFile):
    name = "hwloc"
    description = "Portable abstraction of hierarchical topography of modern hardware architectures"
    license = "BSD-3-Clause"
    url = "https://github.com/conan-io/conan-center-index"
    homepage = "https://www.open-mpi.org/projects/hwloc"
    topics = ("topology", "hardware", "locality")
    package_type = "library"
    settings = "os", "arch", "compiler", "build_type"
    options = {
        "shared": [True, False],
        "fPIC": [True, False],
        "enable_plugins": [True, False],
        "with_opencl": [True, False],
    }
    default_options = {
        "shared": False,
        "fPIC": True,
        "enable_plugins": True,
        "with_opencl": True,
    }

    @property
    def _settings_build(self):
        return getattr(self, "settings_build", self.settings)

    def export_sources(self):
        export_conandata_patches(self)

    def config_options(self):
        if self.settings.os == "Windows":
            del self.options.fPIC

    def configure(self):
        if self.options.shared:
            self.options.rm_safe("fPIC")
        # for plain C projects only
        self.settings.rm_safe("compiler.libcxx")
        self.settings.rm_safe("compiler.cppstd")

    def layout(self):
        basic_layout(self, src_folder="src")

    def requirements(self):
        self.requires("cairo/1.17.6")
        self.requires("libxml2/2.10.4")
        # self.requires("xorg/system")
        # If plugin: shared, else static
        # If not plugin: static ->
        # Investigate: https://docs.conan.io/2/reference/conanfile/methods/requirements.html
        # transitive_libs=True|False?
        self.requires("libpciaccess/0.17")
        self.requires("libudev/system")
        #self.requires("libcpuid/0.5.1") not conan v2
        #self.requires("opengl/system") # Need Nvidia GL
        self.requires("libnuma/2.0.14") # Only for tests?
        if self.options.with_opencl:
            self.requires("opencl-headers/2022.09.30")
            self.requires("opencl-icd-loader/2022.09.30")

    def validate(self):
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
            f"--enable-debug={yes_no(self.settings.build_type == 'Debug')}",
            f"--enable-plugins={yes_no(self.options.enable_plugins)}",
            "--enable-doxygen=no",
            "--enable-picky=no",
            "--enable-cairo=yes",
            "--enable-libxml2=yes",
            "--enable-cpuid=no",  #TODO: missing conan v2
            "--enable-io=yes",
            "--enable-pci=yes",
            "--enable-libudev=yes",
            f"--enable-opencl={yes_no(self.options.with_opencl)}",
            "--enable-manpages=no",
        ])
        """ TODO: none of these are available in in conan or as system package(?)
        "--enable-gl=yes",        # NVIDIA GL
        "--enable-cuda=yes",      #TODO
        "--enable-nvml=yes",      #TODO
        "--enable-rocm=yes",      # Radeon open compute platform smi
        "--enable-levelzero=yes", # oneapi Level Zero """
        tc.generate()
        tc = PkgConfigDeps(self)
        tc.generate()
        tc = AutotoolsDeps(self)
        tc.generate()

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
        copy(self, pattern="LICENSE", src=self.source_folder, dst=os.path.join(self.package_folder, "licenses"))
        autotools = Autotools(self)
        autotools.install()

        rm(self, "*.la", os.path.join(self.package_folder, "lib"))
        rmdir(self, os.path.join(self.package_folder, "lib", "pkgconfig"))
        rmdir(self, os.path.join(self.package_folder, "share"))

        fix_apple_shared_install_name(self)

    def package_info(self):
        self.cpp_info.libs = ["hwloc"]

        self.cpp_info.set_property("pkg_config_name", "hwloc")

        if self.settings.os in ["Linux", "FreeBSD"]:
            self.cpp_info.system_libs.extend(["dl", "m", "pthread"])
