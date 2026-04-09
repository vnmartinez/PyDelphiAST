unit SimpleUnit;

{$IFDEF FPC}
  {$mode delphi}
{$ENDIF}

interface

uses
  SysUtils,
  Classes,
  Vcl.Dialogs;

const
  MAX_ITEMS = 100;
  APP_NAME  = 'MyApp';

type
  TDirection = (dNorth, dSouth, dEast, dWest);
  TDirections = set of TDirection;

  TPoint = record
    X, Y: Double;
    procedure Move(DX, DY: Double);
  end;

  ISerializable = interface
    ['{12345678-1234-1234-1234-123456789ABC}']
    function Serialize: string;
    procedure Deserialize(const Data: string);
  end;

  TAnimal = class
  private
    FName : string;
    FAge  : Integer;
    FTags : TStringList;
  protected
    procedure DoSpeak; virtual; abstract;
  public
    constructor Create(const AName: string; AAge: Integer);
    destructor  Destroy; override;

    function  Clone: TAnimal; virtual;
    procedure Speak;

    class function Species: string; virtual;
    class var InstanceCount: Integer;

    property Name: string  read FName write FName;
    property Age : Integer read FAge  write FAge  default 0;
  published
    property Tags: TStringList read FTags;
  end;

  TDog = class(TAnimal, ISerializable)
  private
    FBreed: string;
    function Serialize: string;
    procedure Deserialize(const Data: string);
  protected
    procedure DoSpeak; override;
  public
    constructor Create(const AName, ABreed: string; AAge: Integer);
    property Breed: string read FBreed write FBreed;
  end;

  TAnimalFactory = class
  public
    class function CreateAnimal(const Kind: string): TAnimal;
  end;

var
  GlobalAnimal: TAnimal;

function  AddIntegers(A, B: Integer): Integer;
procedure PrintLine(const S: string; Count: Integer = 1);

implementation

uses
  System.SysUtils;

{---------------------------------------------------------------------------}
{ TPoint                                                                    }
{---------------------------------------------------------------------------}

procedure TPoint.Move(DX, DY: Double);
begin
  X := X + DX;
  Y := Y + DY;
end;

{---------------------------------------------------------------------------}
{ TAnimal                                                                   }
{---------------------------------------------------------------------------}

constructor TAnimal.Create(const AName: string; AAge: Integer);
begin
  inherited Create;
  FName := AName;
  FAge  := AAge;
  FTags := TStringList.Create;
  Inc(InstanceCount);
end;

destructor TAnimal.Destroy;
begin
  Dec(InstanceCount);
  FTags.Free;
  inherited;
end;

function TAnimal.Clone: TAnimal;
begin
  Result := TAnimalFactory.CreateAnimal(ClassName);
  Result.FName := FName;
  Result.FAge  := FAge;
end;

procedure TAnimal.Speak;
begin
  DoSpeak;
end;

class function TAnimal.Species: string;
begin
  Result := 'Unknown';
end;

{---------------------------------------------------------------------------}
{ TDog                                                                      }
{---------------------------------------------------------------------------}

constructor TDog.Create(const AName, ABreed: string; AAge: Integer);
begin
  inherited Create(AName, AAge);
  FBreed := ABreed;
end;

procedure TDog.DoSpeak;
begin
  WriteLn(Format('%s says: Woof!', [Name]));
end;

function TDog.Serialize: string;
begin
  Result := Format('Dog:%s:%s:%d', [Name, FBreed, Age]);
end;

procedure TDog.Deserialize(const Data: string);
var
  Parts: TStringDynArray;
begin
  Parts := SplitString(Data, ':');
  if Length(Parts) >= 4 then
  begin
    FName  := Parts[1];
    FBreed := Parts[2];
    FAge   := StrToIntDef(Parts[3], 0);
  end;
end;

{---------------------------------------------------------------------------}
{ TAnimalFactory                                                            }
{---------------------------------------------------------------------------}

class function TAnimalFactory.CreateAnimal(const Kind: string): TAnimal;
begin
  if Kind = 'TDog' then
    Result := TDog.Create('', '', 0)
  else
    Result := TAnimal.Create('', 0);
end;

{---------------------------------------------------------------------------}
{ Standalone routines                                                       }
{---------------------------------------------------------------------------}

function AddIntegers(A, B: Integer): Integer;
begin
  Result := A + B;
end;

procedure PrintLine(const S: string; Count: Integer = 1);
var
  I: Integer;
begin
  for I := 1 to Count do
    WriteLn(S);
end;

initialization
  TAnimal.InstanceCount := 0;

finalization
  FreeAndNil(GlobalAnimal);

end.
