#!/bin/bash
BACKUP_DIR=/opt/odoo/backups
DB=wb123data
DATE=$(date +%Y%m%d_%H%M)
FILE="$BACKUP_DIR/${DB}_$DATE.dump"
sudo -u postgres pg_dump -Fc $DB > "$FILE"
echo "Backup: $FILE ($(du -h $FILE | cut -f1))"
find $BACKUP_DIR -name "${DB}_*.dump" -mtime +7 -delete