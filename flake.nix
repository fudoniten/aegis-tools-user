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

        pythonPkgs = pkgs.python3.withPackages (ps: with ps; [ typer pytest ]);

        # Build the Python package
        aegisUserPackage = pkgs.python3Packages.buildPythonApplication {
          pname = "aegis-tools-user";
          version = "0.1.0";
          pyproject = true;

          src = ./.;

          nativeBuildInputs = with pkgs.python3Packages; [ setuptools wheel ];

          propagatedBuildInputs = with pkgs.python3Packages; [ typer ];

          # Don't run tests during build
          doCheck = false;
        };

      in {
        devShells.default = pkgs.mkShell {
          buildInputs = [ pythonPkgs pkgs.age pkgs.git ];

          shellHook = ''
            export PYTHONPATH="$PWD:$PYTHONPATH"
            echo "Aegis User Tools development environment"
            echo ""
            echo "Run: aegis-user --help"
          '';
        };

        packages = {
          default = self.packages.${system}.aegis-user;

          # The main CLI package with all runtime dependencies
          aegis-user = pkgs.writeShellApplication {
            name = "aegis-user";
            runtimeInputs = [ aegisUserPackage pkgs.age pkgs.git ];
            text = ''
              exec aegis-user "$@"
            '';
          };
        };

        # Overlay for use in NixOS configurations  
        overlays.default = final: prev: {
          aegis-user = self.packages.${system}.aegis-user;
        };
      }) // {
        # System-independent outputs
        overlays.default = final: prev: {
          aegis-user = self.packages.${prev.system}.aegis-user;
        };
      };
}
