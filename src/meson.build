pkgdatadir = get_option('prefix') / get_option('datadir') / meson.project_name()

install_subdir('api',     install_dir: pkgdatadir)
install_subdir('views',   install_dir: pkgdatadir)
install_subdir('widgets', install_dir: pkgdatadir)

foreach f : ['application.py', 'main.py']
  install_data(f, install_dir: pkgdatadir)
endforeach
