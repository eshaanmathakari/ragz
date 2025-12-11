{ pkgs }: {
  deps = [
    # Python runtime (handled by Replit's Python module)
    # System dependencies for Playwright browsers
    
    # Core browser dependencies
    pkgs.nss
    pkgs.nspr
    pkgs.atk
    pkgs.at-spi2-atk
    pkgs.cups
    pkgs.libdrm
    pkgs.gtk3
    pkgs.gdk-pixbuf
    pkgs.pango
    pkgs.cairo
    pkgs.alsa-lib
    pkgs.wayland
    pkgs.libxkbcommon
    pkgs.xorg.libX11
    pkgs.xorg.libXcomposite
    pkgs.xorg.libXdamage
    pkgs.xorg.libXext
    pkgs.xorg.libXfixes
    pkgs.xorg.libXrandr
    pkgs.xorg.libXrender
    pkgs.xorg.libXScrnSaver
    pkgs.xorg.libxshmfence
    pkgs.mesa
    pkgs.glib
    
    # Additional libraries for Chromium
    pkgs.expat
    pkgs.fontconfig
    pkgs.freetype
    pkgs.zlib
    
    # Development tools (optional, but useful)
    pkgs.python311
  ];
}
