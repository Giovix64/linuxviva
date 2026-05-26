app_id = 'io.github.giomarco2107.LinuxViva'
pkgdatadir = get_option('prefix') / get_option('datadir') / meson.project_name()

# Desktop entry
install_data(
  app_id + '.desktop',
  install_dir: get_option('datadir') / 'applications',
)

# Launcher wrapper script
conf = configuration_data()
conf.set('PKGDATADIR', pkgdatadir)
conf.set('PYTHON', python.full_path())

configure_file(
  input:  'linuxviva.in',
  output: 'linuxviva',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
)
