#include <REGX52.H>
#include "LCD1602.h"
#include "DS18B20.h"
#include "Delay.h"
#include <intrins.h>

float T;

void UART_Init(void)
{
	SCON=0x50;		//8位数据，可变波特率，允许接收
	TMOD&=0x0F;
	TMOD|=0x20;		//定时器1模式2
	TH1=0xFD;		//11.0592MHz下9600波特率
	TL1=0xFD;
	TR1=1;
	TI=1;
}

void UART_SendByte(unsigned char Byte)
{
	SBUF=Byte;
	while(TI==0);
	TI=0;
}

void UART_SendString(char *String)
{
	while(*String)
	{
		UART_SendByte(*String++);
	}
}

void UART_SendTemperature(float Temp)
{
	unsigned int IntPart;
	unsigned int DecPart;

	UART_SendString("Temp=");
	if(Temp<0)
	{
		UART_SendByte('-');
		Temp=-Temp;
	}
	else
	{
		UART_SendByte('+');
	}

	IntPart=(unsigned int)Temp;
	DecPart=(unsigned int)(Temp*10000)%10000;

	UART_SendByte(IntPart/100+'0');
	UART_SendByte(IntPart/10%10+'0');
	UART_SendByte(IntPart%10+'0');
	UART_SendByte('.');
	UART_SendByte(DecPart/1000+'0');
	UART_SendByte(DecPart/100%10+'0');
	UART_SendByte(DecPart/10%10+'0');
	UART_SendByte(DecPart%10+'0');
	UART_SendString(" C\r\n");
}

void main()
{
	UART_Init();
	LCD_Init();
	LCD_ShowString(1,1,"Temperature:");
	
	// 发送启动信息
	UART_SendString("MCU Started!\r\n");
	Delay(100);
	
	while(1)
	{
		// 尝试读取温度，如果失败则发送错误信息
		DS18B20_ConvertT();	//启动温度转换
		Delay(1000);		//等待转换完成，避免读到旧值
		T=DS18B20_ReadT();	//读取温度
		
		UART_SendTemperature(T);
		
		if(T<0)				//如果温度小于0
		{
			LCD_ShowChar(2,1,'-');	//显示负号
			T=-T;			//将温度变为正数
		}
		else				//如果温度大于等于0
		{
			LCD_ShowChar(2,1,'+');	//显示正号
		}
		LCD_ShowNum(2,2,T,3);		//显示温度整数部分
		LCD_ShowChar(2,5,'.');		//显示小数点
		LCD_ShowNum(2,6,(unsigned long)(T*10000)%10000,4);//显示温度小数部分
	}
}
