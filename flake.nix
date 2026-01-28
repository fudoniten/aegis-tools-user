{
  description = "Aegis User Tools - Self-service secrets management";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };

        python = pkgs.python3.withPackages (ps: with ps; [ typer pytest ]);

      in {
        devShells.default = pkgs.mkShell {
          buildInputs = [ python pkgs.age pkgs.git ];

          shellHook = ''
            export PYTHONPATH="$PWD:$PYTHONPATH"
            echo "Aegis User Tools development environment"
            echo ""
            echo "Run: python -m aegis_user.cli --help"
          '';
        };

        packages.default = pkgs.writeShellScriptBin "aegis-user" ''
          exec ${python}/bin/python -m aegis_user.cli "$@"
        '';
      });
}
