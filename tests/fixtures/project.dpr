program MyProject;

uses
  Vcl.Forms,
  SimpleUnit in 'simple.pas',
  MainFormUnit in 'MainForm.pas' {MainForm};

{$R *.res}

begin
  Application.Initialize;
  Application.MainFormOnTaskbar := True;
  Application.CreateForm(TMainForm, MainForm);
  Application.Run;
end.
