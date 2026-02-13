  {
  inputs.artiq.url = "git+https://github.com/QuantumQuadrate/madmax-artiq.git?ref=release-7";
  inputs.extrapkg.url = "git+https://git.m-labs.hk/M-Labs/artiq-extrapkg.git?ref=release-7";
  inputs.extrapkg.inputs.artiq.follows = "artiq";

  outputs = { self, artiq, extrapkg }:
    let
      pkgs = artiq.inputs.nixpkgs.legacyPackages.x86_64-linux;
      aqmain = artiq.packages.x86_64-linux;

      # Adjust if your entangler checkout is elsewhere
      entanglerPkg = pkgs.python3Packages.buildPythonPackage {
        pname = "entangler";
        version = "0.0.0";
        src = ./entangler;
        format = "pyproject"; # change to "setuptools" if needed
        propagatedBuildInputs = [ ];
      };
    in {
      defaultPackage.x86_64-linux = pkgs.buildEnv {
        name = "artiq-env";
        paths = [
          (pkgs.python3.withPackages(ps: [
            aqmain.artiq
            entanglerPkg
          ]))

          # Toolchain bits ARTIQ needs at runtime
          pkgs.llvmPackages.lld
          pkgs.llvmPackages.llvm
        ];
      };
    };

  nixConfig = {
    extra-trusted-public-keys = "nixbld.m-labs.hk-1:5aSRVA5b320xbNvu30tqxVPXpld73bhtOeH6uAjRyHc=";
    extra-substituters = "https://nixbld.m-labs.hk";
  };
}
