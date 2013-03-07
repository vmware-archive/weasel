#include <ext2fs/ext2fs.h>
#include <linux/ext2_fs.h>
#include <uuid/uuid.h>
#include <stdio.h>

int main(int argc, char *argv[]) {
    ext2_filsys fsys;
    char uuid[100];
    int rc = 0;

    if (argc == 1 || argc > 2 || argv[1] == "-h" || argv[1] == "--help") { 
        printf("usage: %s partition\n", argv[0]);
        return;
    }

    rc = ext2fs_open(argv[1], EXT2_FLAG_FORCE, 0, 0, unix_io_manager, &fsys);

    if (rc) {
        printf("Couldn't open device: %s\n", argv[1]);
        return;
    }

    memset(uuid, 0, sizeof(uuid));
    uuid_unparse(fsys->super->s_uuid, uuid);

    ext2fs_close(fsys);

    printf("%s\n", uuid);

}
