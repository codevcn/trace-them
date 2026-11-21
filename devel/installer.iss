#ifndef MyAppVersion
  #define MyAppVersion "0.2.1"
#endif

#define MyAppName "Trace Them"
#define MyAppPublisher "Trace Them Contributors"
#define MyAppURL "https://github.com/codevcn/trace-them"
#define MyAppExeName "trace-them.exe"

[Setup]
AppId={{8C7B6E3A-4D5A-4E8B-9F2D-1C3A5E7F9B20}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={localappdata}\Programs\Trace Them
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=..\LICENSE
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=trace-them-setup-{#MyAppVersion}
SetupIconFile=..\docs\images\trace-them.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ChangesEnvironment=yes
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "addpath"; Description: "Add Trace Them to your user PATH (recommended)"; GroupDescription: "CLI Environment:"
Name: "skill_antigravity"; Description: "Install global skill for Antigravity (~/.gemini/config/skills/trace-them)"; GroupDescription: "AI Agent Global Skills:"
Name: "skill_codex"; Description: "Install global skill for Codex (~/.codex/skills/trace-them)"; GroupDescription: "AI Agent Global Skills:"
Name: "skill_claude"; Description: "Install global skill for Claude Code (~/.claude/skills/trace-them)"; GroupDescription: "AI Agent Global Skills:"

[Files]
Source: "..\dist\trace-them\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\NOTICE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\skills\trace-them\*"; DestDir: "{app}\skills\trace-them"; Flags: ignoreversion recursesubdirs createallsubdirs

; Global AI agent skills + ownership markers for safe clean uninstall
Source: "..\skills\trace-them\*"; DestDir: "{code:GetAntigravitySkillDir}"; Tasks: skill_antigravity; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\devel\skill-managed.marker"; DestDir: "{code:GetAntigravitySkillDir}"; DestName: ".trace-them-managed"; Tasks: skill_antigravity; Flags: ignoreversion

Source: "..\skills\trace-them\*"; DestDir: "{code:GetCodexSkillDir}"; Tasks: skill_codex; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\devel\skill-managed.marker"; DestDir: "{code:GetCodexSkillDir}"; DestName: ".trace-them-managed"; Tasks: skill_codex; Flags: ignoreversion

Source: "..\skills\trace-them\*"; DestDir: "{code:GetClaudeSkillDir}"; Tasks: skill_claude; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\devel\skill-managed.marker"; DestDir: "{code:GetClaudeSkillDir}"; DestName: ".trace-them-managed"; Tasks: skill_claude; Flags: ignoreversion

[Icons]
Name: "{group}\Trace Them Documentation"; Filename: "{app}\README.md"
Name: "{group}\Uninstall Trace Them"; Filename: "{uninstallexe}"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\skills"

[Code]
function GetUserHome(Param: string): string;
begin
  Result := GetEnv('USERPROFILE');
  if Result = '' then
    Result := ExpandConstant('{localappdata}\..\..');
end;

function GetAntigravitySkillDir(Param: string): string;
begin
  Result := AddBackslash(GetUserHome('')) + '.gemini\config\skills\trace-them';
end;

function GetCodexSkillDir(Param: string): string;
begin
  Result := AddBackslash(GetUserHome('')) + '.codex\skills\trace-them';
end;

function GetClaudeSkillDir(Param: string): string;
begin
  Result := AddBackslash(GetUserHome('')) + '.claude\skills\trace-them';
end;

function StripTrailingBackslash(const PathValue: string): string;
begin
  Result := PathValue;
  while (Length(Result) > 3) and (Result[Length(Result)] = '\') do
    Delete(Result, Length(Result), 1);
end;

function PathContainsEntry(const PathList, Entry: string): Boolean;
var
  Remaining, Segment, Target: string;
  SepPos: Integer;
begin
  Result := False;
  Target := Lowercase(StripTrailingBackslash(Trim(Entry)));
  Remaining := PathList;
  while Remaining <> '' do
  begin
    SepPos := Pos(';', Remaining);
    if SepPos > 0 then
    begin
      Segment := Copy(Remaining, 1, SepPos - 1);
      Delete(Remaining, 1, SepPos);
    end
    else
    begin
      Segment := Remaining;
      Remaining := '';
    end;
    if Lowercase(StripTrailingBackslash(Trim(Segment))) = Target then
    begin
      Result := True;
      Exit;
    end;
  end;
end;

function RemovePathEntry(const PathList, Entry: string): string;
var
  Remaining, Segment, Target, CleanSeg: string;
  SepPos: Integer;
begin
  Result := '';
  Target := Lowercase(StripTrailingBackslash(Trim(Entry)));
  Remaining := PathList;
  while Remaining <> '' do
  begin
    SepPos := Pos(';', Remaining);
    if SepPos > 0 then
    begin
      Segment := Copy(Remaining, 1, SepPos - 1);
      Delete(Remaining, 1, SepPos);
    end
    else
    begin
      Segment := Remaining;
      Remaining := '';
    end;
    CleanSeg := Trim(Segment);
    if (CleanSeg <> '') and (Lowercase(StripTrailingBackslash(CleanSeg)) <> Target) then
    begin
      if Result <> '' then
        Result := Result + ';';
      Result := Result + CleanSeg;
    end;
  end;
end;

procedure AddToUserPath(const DirPath: string);
var
  OrigPath, CleanDir, NewPath: string;
begin
  CleanDir := StripTrailingBackslash(DirPath);
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OrigPath) then
    OrigPath := '';
  if PathContainsEntry(OrigPath, CleanDir) then
    Exit;
  if Trim(OrigPath) = '' then
    NewPath := CleanDir
  else if OrigPath[Length(OrigPath)] = ';' then
    NewPath := OrigPath + CleanDir
  else
    NewPath := OrigPath + ';' + CleanDir;
  RegWriteExpandStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', NewPath);
end;

procedure RemoveFromUserPath(const DirPath: string);
var
  OrigPath, NewPath: string;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OrigPath) then
    Exit;
  NewPath := RemovePathEntry(OrigPath, DirPath);
  if NewPath <> OrigPath then
    RegWriteExpandStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', NewPath);
end;

procedure RemoveManagedSkillDir(const SkillDir: string);
begin
  if DirExists(SkillDir) and FileExists(AddBackslash(SkillDir) + '.trace-them-managed') then
    DelTree(SkillDir, True, True, True);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('addpath') then
    AddToUserPath(ExpandConstant('{app}'));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    RemoveManagedSkillDir(GetAntigravitySkillDir(''));
    RemoveManagedSkillDir(GetCodexSkillDir(''));
    RemoveManagedSkillDir(GetClaudeSkillDir(''));
  end
  else if CurUninstallStep = usPostUninstall then
  begin
    RemoveFromUserPath(ExpandConstant('{app}'));
  end;
end;
