# Chill With You and Spotify

Windows 版「Chill with You Lo-Fi Story」を Proton で起動し、 BepInEx を通じて、 Spotify と Chill with You の連携用のプラグインと bridge を起動します。

![ingame](ingame.png)
## 導入

```sh
nix run path:.#install       # ゲームに BepInEx を配置
nix profile add path:.      # 起動ラッパーをインストール
```

標準の Steam ライブラリ以外にインストールしている場合は、`Chill With You.exe` があるフォルダーを渡します。

```sh
nix run path:.#install -- '/path/to/Chill with You Lo-Fi Story'
```

Steam のプロパティで、このゲームの起動オプションを次に設定します。

```text
/home/username/.nix-profile/bin/chill-with-you-modded %command%
```
ラッパーが、この起動にだけ `winhttp` の DLL override を設定します。
