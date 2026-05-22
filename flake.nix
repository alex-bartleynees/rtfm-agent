{
  description = "rag-ai dev shell";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
            # Python
            python312
            python312Packages.pip
            uv                        # fast venv/dep management

            # Database tooling
            postgresql_17             # gives you psql client
            redis                     # gives you redis-cli

            # Infra
            docker-compose

            # Useful dev tools
            just                      # taskrunner, good companion to a Justfile
            jq
            curl
          ];

          shellHook = ''
            echo "rag-ai dev shell"

            # Create a local venv if one doesn't exist
            if [ ! -d .venv ]; then
              echo "Creating .venv..."
              uv venv .venv
            fi

            source .venv/bin/activate

            # Ensure .env exists so docker-compose doesn't complain
            if [ ! -f .env ]; then
              echo "Warning: no .env file found. Copy .env.example if you have one."
            fi
          '';

          # Helps psycopg / other C-ext packages find libs at build time
          LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
            pkgs.libpq
            pkgs.openssl
          ];
        };
      }
    );
}
