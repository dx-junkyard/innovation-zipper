#!/usr/bin/env node
/**
 * Team Brain Extension Build Script
 *
 * Chrome拡張をパッケージングしてzipファイルを生成します。
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const ROOT_DIR = path.resolve(__dirname, '..');
const DIST_DIR = path.join(ROOT_DIR, 'dist');
const OUTPUT_ZIP = path.join(ROOT_DIR, 'team-brain-extension.zip');

// ビルドに含めるファイル
const FILES_TO_INCLUDE = [
  'manifest.json',
  'src/popup.html',
  'src/popup.js',
  'src/content.js',
  'src/background.js',
  'src/styles.css',
  'src/config.js',
  'icons/icon16.png',
  'icons/icon48.png',
  'icons/icon128.png'
];

/**
 * ディストリビューションディレクトリを作成
 */
function createDistDir() {
  if (fs.existsSync(DIST_DIR)) {
    fs.rmSync(DIST_DIR, { recursive: true });
  }
  fs.mkdirSync(DIST_DIR, { recursive: true });
  fs.mkdirSync(path.join(DIST_DIR, 'src'), { recursive: true });
  fs.mkdirSync(path.join(DIST_DIR, 'icons'), { recursive: true });
}

/**
 * ファイルをコピー
 */
function copyFiles() {
  for (const file of FILES_TO_INCLUDE) {
    const srcPath = path.join(ROOT_DIR, file);
    const destPath = path.join(DIST_DIR, file);

    if (fs.existsSync(srcPath)) {
      // ディレクトリが存在することを確認
      const destDir = path.dirname(destPath);
      if (!fs.existsSync(destDir)) {
        fs.mkdirSync(destDir, { recursive: true });
      }

      fs.copyFileSync(srcPath, destPath);
      console.log(`✓ Copied: ${file}`);
    } else {
      console.warn(`⚠ Warning: ${file} not found, skipping...`);
    }
  }
}

/**
 * アイコンが存在しない場合はプレースホルダーを生成
 */
function ensureIcons() {
  const iconSizes = [16, 48, 128];
  const iconsDir = path.join(DIST_DIR, 'icons');

  for (const size of iconSizes) {
    const iconPath = path.join(iconsDir, `icon${size}.png`);
    if (!fs.existsSync(iconPath)) {
      // シンプルなプレースホルダーPNGを生成（1x1ピクセルの青い画像）
      // 本番環境では適切なアイコンに差し替えてください
      console.log(`⚠ Icon icon${size}.png not found, creating placeholder...`);

      // PNG header + minimal IDAT chunk (1x1 blue pixel)
      // これは非常にシンプルなプレースホルダーです
      const pngData = Buffer.from([
        0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, // PNG signature
        0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52, // IHDR chunk
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
        0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
        0xde, 0x00, 0x00, 0x00, 0x0c, 0x49, 0x44, 0x41, // IDAT chunk (blue pixel)
        0x54, 0x08, 0xd7, 0x63, 0x68, 0xf8, 0xcf, 0xc0,
        0x00, 0x00, 0x02, 0x0d, 0x01, 0x03, 0x8c, 0x4c,
        0x29, 0x42, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, // IEND chunk
        0x4e, 0x44, 0xae, 0x42, 0x60, 0x82
      ]);
      fs.writeFileSync(iconPath, pngData);
    }
  }
}

/**
 * zipファイルを作成
 */
function createZip() {
  // 既存のzipを削除
  if (fs.existsSync(OUTPUT_ZIP)) {
    fs.unlinkSync(OUTPUT_ZIP);
  }

  // zipコマンドを使用（大多数のLinux/Mac環境で利用可能）
  try {
    execSync(`cd "${DIST_DIR}" && zip -r "${OUTPUT_ZIP}" .`, { stdio: 'inherit' });
    console.log(`\n✓ Created: ${OUTPUT_ZIP}`);
  } catch (error) {
    console.error('Error creating zip file. Make sure "zip" command is available.');
    console.error('On Ubuntu/Debian: sudo apt-get install zip');
    process.exit(1);
  }
}

/**
 * クリーンアップ
 */
function cleanup() {
  if (fs.existsSync(DIST_DIR)) {
    fs.rmSync(DIST_DIR, { recursive: true });
    console.log('✓ Cleaned up dist directory');
  }
}

// メイン処理
console.log('🔨 Building Team Brain Extension...\n');

try {
  createDistDir();
  copyFiles();
  ensureIcons();
  createZip();
  cleanup();
  console.log('\n🎉 Build completed successfully!');
  console.log(`   Output: ${OUTPUT_ZIP}`);
} catch (error) {
  console.error('Build failed:', error);
  process.exit(1);
}
