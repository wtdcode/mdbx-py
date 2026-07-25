#include "libmdbx/mdbx.h"
#include <stdio.h>

int main(void) {
    printf("{\n");
    printf("  \"MDBX_SUCCESS\": %d,\n", MDBX_SUCCESS);
    printf("  \"MDBX_ENODATA\": %d,\n", MDBX_ENODATA);
    printf("  \"MDBX_EINVAL\": %d,\n", MDBX_EINVAL);
    printf("  \"MDBX_EACCES\": %d,\n", MDBX_EACCESS);
    printf("  \"MDBX_ENOMEM\": %d,\n", MDBX_ENOMEM);
    printf("  \"MDBX_EROFS\": %d,\n", MDBX_EROFS);
    printf("  \"MDBX_ENOSYS\": %d,\n", MDBX_ENOSYS);
    printf("  \"MDBX_EIO\": %d,\n", MDBX_EIO);
    printf("  \"MDBX_EPERM\": %d,\n", MDBX_EPERM);
    printf("  \"MDBX_EINTR\": %d,\n", MDBX_EINTR);
    printf("  \"MDBX_ENOFILE\": %d,\n", MDBX_ENOFILE);
    printf("  \"MDBX_EREMOTE\": %d\n", MDBX_EREMOTE);
    printf("}\n");
    return 0;
}
