require('dotenv').config();
const { google } = require('googleapis');

const SCOPES = [
  'https://www.googleapis.com/auth/documents',
  'https://www.googleapis.com/auth/drive',
];

function getRequiredEnv(name) {
  const value = process.env[name];
  if (!value || !value.trim()) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

function normalizePrivateKey(rawValue) {
  let value = rawValue.trim();

  if (
    (value.startsWith('"') && value.endsWith('"')) ||
    (value.startsWith("'") && value.endsWith("'"))
  ) {
    value = value.slice(1, -1);
  }

  value = value.replace(/\\n/g, '\n');

  if (!value.includes('-----BEGIN') && !value.includes('-----END')) {
    try {
      const decoded = Buffer.from(value, 'base64').toString('utf8').trim();
      if (decoded.includes('-----BEGIN') && decoded.includes('-----END')) {
        value = decoded;
      }
    } catch (_error) {
      // Ignore and continue with the original value.
    }
  }

  if (!value.includes('-----BEGIN') || !value.includes('-----END')) {
    throw new Error(
      'GOOGLE_PRIVATE_KEY is not in a valid PEM format. Provide a full service-account private key (with BEGIN/END markers), escaped newlines, or base64-encoded PEM.'
    );
  }

  return value.trim();
}

function getAuthClient() {
  const keyFile = process.env.GOOGLE_APPLICATION_CREDENTIALS || process.env.GOOGLE_SERVICE_ACCOUNT_KEY_FILE;
  if (keyFile && keyFile.trim()) {
    return new google.auth.GoogleAuth({ keyFile: keyFile.trim(), scopes: SCOPES });
  }

  const clientEmail = getRequiredEnv('GOOGLE_CLIENT_EMAIL');
  const privateKeyRaw = getRequiredEnv('GOOGLE_PRIVATE_KEY');
  const privateKey = normalizePrivateKey(privateKeyRaw);

  return new google.auth.GoogleAuth({
    credentials: {
      client_email: clientEmail,
      private_key: privateKey,
    },
    scopes: SCOPES,
  });
}

module.exports = { getAuthClient };