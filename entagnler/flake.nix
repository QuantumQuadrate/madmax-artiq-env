{
  description = "ARTIQ env (artiq-extrapkg release-8)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
    extrapkg.url = "git+https://git.m-labs.hk/M-Labs/artiq-extrapkg.git?ref=release-8";

    # Optional but recommended: keep extrapkg using the same nixpkgs
    extrapkg.inputs.nixpkgs.follows = "nixpkgs";

    entangler-core = {
      url = "git+https://github.com/QuantumQuadrate/madmax-entangler-core.git";
      inputs.nixpkgs.follows = "extrapkg/daxpkgs/nixpkgs";
    };
  };

  outputs = { self, nixpkgs, extrapkg, entangler-core }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
      entangler = entangler-core.packages.${system}.default;

      aq = extrapkg.packages.${system};

      pythonEnv = pkgs.python3.withPackages (ps: [
        aq.artiq
        # aq.flake8-artiq
        aq.dax
        entangler
        # aq.dax-applets
      ]);
    in
    {
      # ✅ nix develop
      devShells.${system}.default = pkgs.mkShell {
        packages = [
          pythonEnv
          # add non-python tools here if you want them in dev shell:
          # pkgs.git
        ];
      };

      # ✅ nix build / nix profile install
      packages.${system}.default = pkgs.buildEnv {
        name = "artiq-env";
        paths = [
          pythonEnv
          # add non-python packages here if desired:
          # aq.openocd-bscanspi
          # pkgs.gtkwave
        ];
      };
    };

  nixConfig = {
    extra-trusted-public-keys =
      "nixbld.m-labs.hk-1:5aSRVA5b320xbNvu30tqxVPXpld73bhtOeH6uAjRyHc=";
    extra-substituters = "https://nixbld.m-labs.hk";
  };
}
