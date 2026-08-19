"""Options dialog for mitmgui with Https / Connections / Gateway tabs."""

import math
import os
import random
import string
import datetime

from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap, QFont, QPen
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mitmproxy.tools.mitmgui.config import AppConfig


class OptionsDialog(QDialog):
    """Configuration dialog with Https / Connections / Gateway tabs."""

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._original_data = self._snapshot()
        self._modified = False

        self.setWindowTitle("Options")
        self.setMinimumSize(500, 400)
        # Generate a gear icon
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        m = 3
        bg = "#546E7A"
        p.setBrush(QColor(bg))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(m, m, 64 - 2 * m, 64 - 2 * m, 12, 12)
        pen = QPen(QColor("white"))
        pen.setWidthF(2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        cx, cy = 32, 32
        r_outer = 11
        p.drawEllipse(QPointF(cx, cy), r_outer, r_outer)
        p.drawEllipse(QPointF(cx, cy), 4, 4)
        for i in range(6):
            angle = i * 60
            rad = math.radians(angle)
            x1 = cx + r_outer * math.cos(rad)
            y1 = cy + r_outer * math.sin(rad)
            x2 = cx + (r_outer + 6) * math.cos(rad)
            y2 = cy + (r_outer + 6) * math.sin(rad)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        p.end()
        self.setWindowIcon(QIcon(pixmap))

        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._create_https_tab(), "HTTPS")
        tabs.addTab(self._create_connections_tab(), "Connections")
        tabs.addTab(self._create_gateway_tab(), "Gateway")
        tabs.addTab(self._create_settings_tab(), "Settings")
        tabs.addTab(self._create_sendto_tab(), "SendTo")
        layout.addWidget(tabs)

        # OK / Cancel buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_ok)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _snapshot(self) -> dict:
        return {
            "https": dict(self._config._data["https"]),
            "connections": dict(self._config._data["connections"]),
            "gateway": dict(self._config._data["gateway"]),
            "settings": dict(self._config._data["settings"]),
            "sendto": list(self._config._data["sendto"]),
        }

    # ── HTTPS Tab ──

    def _create_settings_tab(self) -> QWidget:
        """Settings tab with general options."""
        w = QWidget()
        layout = QVBoxLayout(w)

        self._cl_checkbox = QCheckBox("Auto Adjust Content-Length")
        self._cl_checkbox.setToolTip(
            "When request/response body is modified, automatically update "
            "the Content-Length header to match the actual body size."
        )
        self._cl_checkbox.setChecked(self._config.auto_adjust_content_length)
        layout.addWidget(self._cl_checkbox)

        self._ssl_insecure_cb = QCheckBox("Ignore Server Certificate")
        self._ssl_insecure_cb.setToolTip(
            "When enabled, mitmproxy will not verify SSL/TLS certificates "
            "from upstream servers. Useful for debugging and proxy chaining."
        )
        self._ssl_insecure_cb.setChecked(self._config.ssl_insecure)
        layout.addWidget(self._ssl_insecure_cb)

        layout.addStretch()
        return w

    def _create_sendto_tab(self) -> QWidget:
        """SendTo tab: list of name→proxy-address entries for context-menu forwarding."""
        from PyQt6.QtWidgets import QScrollArea

        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self._sendto_layout = QVBoxLayout(container)
        self._sendto_layout.setContentsMargins(8, 8, 8, 8)
        self._sendto_layout.setSpacing(4)
        scroll.setWidget(container)
        outer.addWidget(scroll)

        self._sendto_rows: list[dict] = []  # each: {"name": QLineEdit, "addr": QLineEdit, "row_widget": QWidget}

        add_btn = QPushButton("＋ Add Row")
        add_btn.clicked.connect(lambda: self._sendto_add_row())
        outer.addWidget(add_btn)

        # Populate from config
        entries = list(self._config.sendto_entries)
        if not entries:
            entries = [{"name": "", "address": ""}]
        for entry in entries:
            self._sendto_add_row(entry.get("name", ""), entry.get("address", ""))

        # At least one row always
        if not self._sendto_rows:
            self._sendto_add_row("", "")

        self._sendto_layout.addStretch()

        return w

    def _sendto_add_row(self, name: str = "", addr: str = "") -> None:
        """Add a SendTo row widget to the layout."""
        from PyQt6.QtWidgets import QSizePolicy

        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(4)

        add_btn = QPushButton("＋")
        add_btn.setFixedWidth(28)
        add_btn.setToolTip("Insert row below")
        add_btn.clicked.connect(lambda: self._sendto_insert_row(row_widget))
        row_layout.addWidget(add_btn)

        del_btn = QPushButton("－")
        del_btn.setFixedWidth(28)
        del_btn.setToolTip("Delete this row")
        del_btn.clicked.connect(lambda: self._sendto_delete_row(row_widget))
        row_layout.addWidget(del_btn)

        name_edit = QLineEdit(name)
        name_edit.setPlaceholderText("SendToName")
        name_edit.setFixedWidth(120)  # ~10 English chars
        row_layout.addWidget(name_edit)

        addr_edit = QLineEdit(addr)
        addr_edit.setPlaceholderText("http://127.0.0.1:8888")
        row_layout.addWidget(addr_edit)

        self._sendto_layout.insertWidget(self._sendto_layout.count() - 1, row_widget)
        self._sendto_rows.append({"name": name_edit, "addr": addr_edit, "row_widget": row_widget})
        self._sendto_update_delete_buttons()

    def _sendto_insert_row(self, after_widget: QWidget) -> None:
        """Insert a new empty row after the given row widget."""
        idx = self._sendto_layout.indexOf(after_widget)
        row_data = {"name": QLineEdit(""), "addr": QLineEdit(""), "row_widget": None}
        # Create the row widget
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(4)

        add_btn = QPushButton("＋")
        add_btn.setFixedWidth(28)
        add_btn.clicked.connect(lambda: self._sendto_insert_row(row_widget))
        row_layout.addWidget(add_btn)

        del_btn = QPushButton("－")
        del_btn.setFixedWidth(28)
        del_btn.clicked.connect(lambda: self._sendto_delete_row(row_widget))
        row_layout.addWidget(del_btn)

        name_edit = QLineEdit("")
        name_edit.setPlaceholderText("SendToName")
        name_edit.setFixedWidth(120)
        row_layout.addWidget(name_edit)

        addr_edit = QLineEdit("")
        addr_edit.setPlaceholderText("http://127.0.0.1:8888")
        row_layout.addWidget(addr_edit)

        row_data["name"] = name_edit
        row_data["addr"] = addr_edit
        row_data["row_widget"] = row_widget

        self._sendto_layout.insertWidget(idx + 1, row_widget)
        # Find position in list
        insert_pos = next(
            (i + 1 for i, r in enumerate(self._sendto_rows) if r["row_widget"] is after_widget),
            len(self._sendto_rows),
        )
        self._sendto_rows.insert(insert_pos, row_data)
        self._sendto_update_delete_buttons()

    def _sendto_delete_row(self, row_widget: QWidget) -> None:
        """Delete a SendTo row (but never delete the last row)."""
        if len(self._sendto_rows) <= 1:
            return
        self._sendto_rows = [r for r in self._sendto_rows if r["row_widget"] is not row_widget]
        self._sendto_layout.removeWidget(row_widget)
        row_widget.deleteLater()
        self._sendto_update_delete_buttons()

    def _sendto_update_delete_buttons(self) -> None:
        """Disable delete button on the first row, enable on others."""
        for i, row in enumerate(self._sendto_rows):
            # Second child is the delete button (index 1 in the HBoxLayout)
            hbox = row["row_widget"].layout()
            if hbox and hbox.count() > 1:
                del_btn = hbox.itemAt(1).widget()
                if del_btn:
                    del_btn.setEnabled(len(self._sendto_rows) > 1)

    def _create_https_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        self._decrypt_cb = QCheckBox("Decrypt HTTPS Traffic")
        self._decrypt_cb.setChecked(self._config.decrypt_https)
        self._decrypt_cb.toggled.connect(self._on_decrypt_toggled)
        layout.addWidget(self._decrypt_cb)

        # Cert options group
        self._cert_group = QGroupBox("Certificate Options")
        cert_layout = QVBoxLayout(self._cert_group)

        # Cert path
        cert_file_row = QHBoxLayout()
        cert_file_row.addWidget(QLabel("Certificate File:"))
        self._cert_path_edit = QLineEdit(self._config.cert_path)
        self._cert_path_edit.setPlaceholderText("Path to PEM certificate file")
        cert_file_row.addWidget(self._cert_path_edit)
        browse_btn = QPushButton("...")
        browse_btn.setFixedWidth(32)
        browse_btn.clicked.connect(self._browse_cert)
        cert_file_row.addWidget(browse_btn)
        cert_layout.addLayout(cert_file_row)

        # Generate button
        gen_row = QHBoxLayout()
        gen_row.addStretch()
        gen_btn = QPushButton("Generate New Certificate")
        gen_btn.clicked.connect(self._generate_cert)
        gen_row.addWidget(gen_btn)
        cert_layout.addLayout(gen_row)

        # Passphrase
        pass_row = QFormLayout()
        self._cert_pass_edit = QLineEdit(self._config.cert_passphrase)
        self._cert_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._cert_pass_edit.setPlaceholderText("Private key passphrase")
        pass_row.addRow("Passphrase:", self._cert_pass_edit)
        cert_layout.addLayout(pass_row)

        layout.addWidget(self._cert_group)

        # Initial visibility
        self._cert_group.setVisible(self._decrypt_cb.isChecked())

        layout.addStretch()
        return w

    def _on_decrypt_toggled(self, checked: bool) -> None:
        self._cert_group.setVisible(checked)
        self._modified = True

    def _browse_cert(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Certificate File", "",
            "Certificate Files (*.p12 *.pfx *.pem *.crt *.key);;PEM Files (*.pem *.crt *.key);;PKCS#12 Files (*.p12 *.pfx);;All Files (*)"
        )
        if path:
            self._cert_path_edit.setText(path)
            self._modified = True

    def _generate_cert(self) -> None:
        """Generate a new self-signed CA certificate (.p12) with public key."""
        try:
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.primitives.serialization import pkcs12

            # Ensure certs directory exists
            certs_dir = os.path.join(os.getcwd(), "certs")
            os.makedirs(certs_dir, exist_ok=True)

            # Generate random 8-char filename
            suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
            cert_filename = f"mitmproxy_{suffix}.p12"
            cert_path = os.path.join(certs_dir, cert_filename)
            pubkey_path = os.path.join(certs_dir, f"mitmproxy_{suffix}_pub.pem")

            # Generate RSA key
            key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
            )

            # Self-signed CA certificate
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Beijing"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "Beijing"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "QinQinYo"),
                x509.NameAttribute(NameOID.COMMON_NAME, "QinQinYo"),
            ])

            now = datetime.datetime.utcnow()
            cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(issuer)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now)
                .not_valid_after(now + datetime.timedelta(days=365 * 100))  # 100 years
                .add_extension(
                    x509.BasicConstraints(ca=True, path_length=None),
                    critical=True,
                )
                .sign(key, hashes.SHA256())
            )

            passphrase = b"QinQinYo"

            # Save as PKCS#12
            p12_data = pkcs12.serialize_key_and_certificates(
                name=b"QinQinYo",
                key=key,
                cert=cert,
                cas=None,
                encryption_algorithm=serialization.BestAvailableEncryption(passphrase),
            )
            with open(cert_path, "wb") as f:
                f.write(p12_data)

            # Save public key as PEM
            pub_key_pem = key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            with open(pubkey_path, "wb") as f:
                f.write(pub_key_pem)

            # Save X.509 certificate in DER format (.cer) so Windows can
            # import it directly into the Trusted Root Certification Authorities store
            cer_filename = f"mitmproxy_{suffix}.cer"
            cer_path = os.path.join(certs_dir, cer_filename)
            with open(cer_path, "wb") as f:
                f.write(cert.public_bytes(serialization.Encoding.DER))

            # Auto-fill relative path and passphrase
            rel_cert = os.path.relpath(cert_path, os.getcwd())
            rel_pub = os.path.relpath(pubkey_path, os.getcwd())
            rel_cer = os.path.relpath(cer_path, os.getcwd())
            self._cert_path_edit.setText(rel_cert)
            self._cert_pass_edit.setText("QinQinYo")
            self._modified = True

            QMessageBox.information(
                self, "Certificate Generated",
                f"Certificate (.p12):  {rel_cert}\n"
                f"Public Key (.pem):   {rel_pub}\n"
                f"Windows Import (.cer): {rel_cer}\n\n"
                f"Issuer:   QinQinYo\n"
                f"Password: QinQinYo\n"
                f"Validity: 100 years\n\n"
                f"On Windows, double-click the .cer file and install it into "
                f"\"Trusted Root Certification Authorities\" to decrypt HTTPS."
            )
        except Exception as e:
            QMessageBox.warning(
                self, "Generation Failed", f"Failed to generate certificate:\n{e}"
            )

    # ── Connections Tab ──

    def _create_connections_tab(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)

        self._listen_host_edit = QLineEdit(self._config.listen_host)
        self._listen_host_edit.setPlaceholderText("127.0.0.1")
        self._listen_host_edit.textChanged.connect(lambda: setattr(self, "_modified", True))
        layout.addRow("Listen IP:", self._listen_host_edit)

        self._listen_port_edit = QLineEdit(str(self._config.listen_port))
        self._listen_port_edit.setPlaceholderText("8080")
        self._listen_port_edit.textChanged.connect(lambda: setattr(self, "_modified", True))
        layout.addRow("Listen Port:", self._listen_port_edit)

        layout.addItem(None)
        return w

    # ── Gateway Tab ──

    def _create_gateway_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        gw_mode = self._config.gateway_mode
        self._gw_system_rb = QRadioButton("Use System Proxy")
        self._gw_system_rb.setChecked(gw_mode == "system")
        self._gw_system_rb.toggled.connect(lambda: setattr(self, "_modified", True))
        layout.addWidget(self._gw_system_rb)

        manual_row = QHBoxLayout()
        self._gw_manual_rb = QRadioButton("Manual Proxy:")
        self._gw_manual_rb.setChecked(gw_mode == "manual")
        self._gw_manual_rb.toggled.connect(self._on_manual_toggled)
        manual_row.addWidget(self._gw_manual_rb)
        self._gw_manual_edit = QLineEdit(
            self._config.manual_proxy
            if self._config.manual_proxy != "http://127.0.0.1:8888"
            else ""
        )
        self._gw_manual_edit.setPlaceholderText("http://127.0.0.1:8888")
        self._gw_manual_edit.textChanged.connect(lambda: setattr(self, "_modified", True))
        self._gw_manual_edit.setEnabled(gw_mode == "manual")
        manual_row.addWidget(self._gw_manual_edit)
        layout.addLayout(manual_row)

        self._gw_none_rb = QRadioButton("No Proxy")
        self._gw_none_rb.setChecked(gw_mode == "no_proxy")
        self._gw_none_rb.toggled.connect(lambda: setattr(self, "_modified", True))
        layout.addWidget(self._gw_none_rb)

        layout.addStretch()
        return w

    def _on_manual_toggled(self, checked: bool) -> None:
        self._gw_manual_edit.setEnabled(checked)
        self._modified = True

    # ── OK / Cancel ──

    def _validate(self) -> list[str]:
        errors = []
        if self._decrypt_cb.isChecked() and not self._cert_path_edit.text().strip():
            errors.append("HTTPS decryption is enabled but no certificate file is selected.")
        else:
            # Validate cert file
            errors.extend(self._validate_cert())
        try:
            port = int(self._listen_port_edit.text())
            if not (1 <= port <= 65535):
                errors.append("Listen port must be between 1 and 65535.")
        except ValueError:
            errors.append("Listen port must be a valid number.")

        if self._gw_manual_rb.isChecked():
            from urllib.parse import urlparse

            proxy = self._gw_manual_edit.text().strip()
            parsed = urlparse(proxy)
            if parsed.scheme not in ("http", "https"):
                errors.append(
                    "Upstream proxy must use http:// or https://. SOCKS5 upstream proxies are not supported."
                )
            elif not parsed.hostname or not parsed.port:
                errors.append("Upstream proxy must include a host and port.")
        return errors

    def _validate_cert(self) -> list[str]:
        """Validate that the certificate file can be loaded.

        Supports PEM and PKCS#12 (.p12/.pfx) formats, mirroring
        CertStore.add_cert_file().
        """
        cert_path = self._cert_path_edit.text().strip()
        if not cert_path:
            return []
        passphrase = self._cert_pass_edit.text() or None

        errors: list[str] = []
        from pathlib import Path

        path = Path(cert_path)

        if path.suffix.lower() in (".p12", ".pfx"):
            return self._validate_p12(path, passphrase, errors)
        else:
            return self._validate_pem(path, passphrase, errors)

    @staticmethod
    def _validate_p12(path, passphrase: str | None, errors: list[str]) -> list[str]:
        """Validate a PKCS#12 file."""
        from cryptography.hazmat.primitives.serialization import pkcs12

        try:
            raw = path.read_bytes()
            pw = passphrase.encode("utf-8") if passphrase else None
            import warnings
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message=r"PKCS#12 bundle could not be parsed as DER",
                )
                private_key, cert, _ = pkcs12.load_key_and_certificates(raw, pw)
        except FileNotFoundError:
            errors.append(f"Certificate file not found: {path}")
            return errors
        except OSError as e:
            errors.append(f"Cannot read certificate file: {e}")
            return errors
        except ValueError as e:
            msg = str(e).lower()
            if "password" in msg or "bad decrypt" in msg or "mac" in msg:
                errors.append(
                    "Certificate passphrase is incorrect.\n"
                    "Please check the passphrase and try again."
                )
            else:
                errors.append(
                    f'Cannot load PKCS#12 file "{path}":\n\n{e}'
                )
            return errors

        if cert is None:
            errors.append(f'No certificate found in "{path}"')
            return errors
        if private_key is None:
            errors.append(f'No private key found in "{path}"')
            return errors

        return errors  # empty = no errors

    @staticmethod
    def _validate_pem(path, passphrase: str | None, errors: list[str]) -> list[str]:
        """Validate a PEM certificate file (original logic)."""
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.x509 import load_pem_x509_certificate

            raw = path.read_bytes()

            try:
                load_pem_x509_certificate(raw)
            except Exception as e:
                errors.append(
                    f'Invalid certificate format for "{path}":\n'
                    f"No valid X.509 certificate found in PEM file.\n\n"
                    f"Details: {e}"
                )
                return errors

            pw_bytes = passphrase.encode("utf-8") if passphrase else None
            try:
                serialization.load_pem_private_key(raw, password=pw_bytes)
            except TypeError:
                errors.append(
                    "Certificate passphrase is incorrect.\n"
                    "Please check the passphrase and try again."
                )
                return errors
            except ValueError as e:
                msg = str(e).lower()
                if "bad decrypt" in msg or "password" in msg or "passphrase" in msg:
                    errors.append(
                        "Certificate passphrase is incorrect.\n"
                        "Please check the passphrase and try again."
                    )
                    return errors

        except FileNotFoundError:
            errors.append(f"Certificate file not found: {path}")
        except OSError as e:
            errors.append(f"Cannot read certificate file: {e}")

        return errors

    def _on_ok(self) -> None:
        errors = self._validate()
        if errors:
            QMessageBox.warning(self, "Validation Error", "\n".join(errors))
            return

        self._config.decrypt_https = self._decrypt_cb.isChecked()
        self._config.cert_path = self._cert_path_edit.text()
        self._config.cert_passphrase = self._cert_pass_edit.text()
        self._config.listen_host = self._listen_host_edit.text() or "127.0.0.1"
        try:
            self._config.listen_port = int(self._listen_port_edit.text())
        except ValueError:
            self._config.listen_port = 8080

        if self._gw_system_rb.isChecked():
            self._config.gateway_mode = "system"
        elif self._gw_manual_rb.isChecked():
            self._config.gateway_mode = "manual"
            manual_val = self._gw_manual_edit.text().strip()
            self._config.manual_proxy = manual_val or "http://127.0.0.1:8888"
        else:
            self._config.gateway_mode = "no_proxy"

        self._config.auto_adjust_content_length = self._cl_checkbox.isChecked()
        self._config.ssl_insecure = self._ssl_insecure_cb.isChecked()

        # SendTo: filter empty rows (name or address blank = empty)
        sendto_entries = []
        for row in self._sendto_rows:
            name = row["name"].text().strip()
            addr = row["addr"].text().strip()
            if name and addr:
                sendto_entries.append({"name": name, "address": addr})
        self._config.sendto_entries = sendto_entries

        self._config.save()
        self.accept()

    @property
    def was_modified(self) -> bool:
        """Check if any HTTPS/connections settings changed (requires proxy restart)."""
        return self._modified
