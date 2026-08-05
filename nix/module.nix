# SPDX-FileCopyrightText: 2026 Michel Oosterhof <michel@oosterhof.net>
#
# SPDX-License-Identifier: BSD-3-Clause

# NixOS module for the Cowrie honeypot: services.cowrie options, a generated
# /etc/cowrie/cowrie.cfg and a hardened systemd service running as a dynamic
# user with its state under /var/lib/cowrie and logs under /var/log/cowrie.

{ self }:
{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.services.cowrie;
  format = pkgs.formats.ini { };
  configFile = format.generate "cowrie.cfg" cfg.settings;
in
{
  options.services.cowrie = {
    enable = lib.mkEnableOption "Cowrie SSH/Telnet honeypot";

    package = lib.mkOption {
      type = lib.types.package;
      default = self.packages.${pkgs.stdenv.hostPlatform.system}.cowrie;
      defaultText = lib.literalExpression "cowrie.packages.\${system}.cowrie";
      description = "Cowrie package to run.";
    };

    settings = lib.mkOption {
      type = format.type;
      default = { };
      example = lib.literalExpression ''
        {
          honeypot.hostname = "svr04";
          ssh.listen_endpoints = "tcp:2222:interface=0.0.0.0";
          telnet.enabled = true;
        }
      '';
      description = ''
        Contents of {file}`/etc/cowrie/cowrie.cfg`. Options not set here
        keep the defaults from the bundled {file}`cowrie.cfg.dist`.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    services.cowrie.settings.honeypot = {
      state_path = lib.mkDefault "/var/lib/cowrie";
      log_path = lib.mkDefault "/var/log/cowrie";
    };

    environment.etc."cowrie/cowrie.cfg".source = configFile;

    systemd.services.cowrie = {
      description = "Cowrie SSH/Telnet honeypot";
      wantedBy = [ "multi-user.target" ];
      after = [ "network.target" ];
      restartTriggers = [ configFile ];

      # Foreground twistd with the stdout logger; the journal keeps the log.
      environment.COWRIE_STDOUT = "yes";

      # The start script requires ./etc/cowrie.cfg as an initialization
      # marker, and etc_path defaults to ./etc, so point both at /etc/cowrie.
      preStart = "ln -sfn /etc/cowrie etc";

      serviceConfig = {
        ExecStart = "${lib.getExe cfg.package} start";
        Restart = "always";
        RestartSec = 5;

        DynamicUser = true;
        StateDirectory = "cowrie";
        LogsDirectory = "cowrie";
        WorkingDirectory = "/var/lib/cowrie";

        CapabilityBoundingSet = [ "" ];
        LockPersonality = true;
        NoNewPrivileges = true;
        PrivateTmp = true;
        ProtectControlGroups = true;
        ProtectHome = true;
        ProtectKernelModules = true;
        ProtectKernelTunables = true;
        ProtectSystem = "strict";
        RestrictAddressFamilies = [
          "AF_INET"
          "AF_INET6"
          "AF_UNIX"
        ];
        RestrictNamespaces = true;
        RestrictRealtime = true;
        RestrictSUIDSGID = true;
        SystemCallArchitectures = "native";
        SystemCallFilter = [
          "@system-service"
          "~@privileged"
        ];
      };
    };
  };
}
